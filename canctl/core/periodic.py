"""PeriodicManager — 스케줄러 스레드 1개로 모든 주기 송신 처리"""

import re
import threading
import time

import can

from .errors import CanctlError, INVALID_ARG, PERIODIC_FAIL
from .output import emit


# --requires 파싱: "0x700:00:100ms"
_REQUIRES_RE = re.compile(
    r"^(0x[0-9A-Fa-f]+):([0-9A-Fa-f]+):(\d+)ms$"
)


def parse_requires(spec: str) -> dict:
    """'0x700:00FF:100ms' → {id: int, data: bytes, interval_s: float}"""
    m = _REQUIRES_RE.match(spec)
    if not m:
        raise CanctlError(
            INVALID_ARG,
            f"--requires format must be ID:DATA:INTERVALms, got: {spec}",
        )
    arb_id = int(m.group(1), 16)
    data = bytes.fromhex(m.group(2))
    interval_s = int(m.group(3)) / 1000.0
    return {"id": arb_id, "data": data, "interval_s": interval_s}


class _Job:
    def __init__(self, arb_id: int, data: bytes, interval_s: float):
        self.arb_id = arb_id
        self.data = data
        self.interval_s = interval_s
        self.msg = can.Message(
            arbitration_id=arb_id,
            data=data,
            is_extended_id=(arb_id > 0x7FF),
        )
        self.next_send = 0.0


class PeriodicManager:
    """스레드 1개 스케줄러로 주기 송신 관리."""

    def __init__(self):
        self._jobs: list[_Job] = []
        self._running = False
        self._thread: threading.Thread | None = None
        self._bus = None
        self._bus_label: str | None = None

    def add_job(self, arb_id: int, data: bytes, interval_ms: int) -> None:
        self._jobs.append(_Job(arb_id, data, interval_ms / 1000.0))

    def add_requires(self, specs: list[str]) -> None:
        """--requires 스펙 목록 파싱 후 job 등록."""
        for spec in specs:
            parsed = parse_requires(spec)
            self.add_job(parsed["id"], parsed["data"],
                         int(parsed["interval_s"] * 1000))

    def start(self, bus, bus_label: str) -> None:
        if not self._jobs:
            return
        self._bus = bus
        self._bus_label = bus_label
        self._running = True
        now = time.monotonic()
        for job in self._jobs:
            job.next_send = now
        self._thread = threading.Thread(
            target=self._loop, daemon=True, name="periodic"
        )
        self._thread.start()

        # periodic_start 이벤트 출력
        for job in self._jobs:
            emit({
                "type": "periodic_start",
                "bus": bus_label,
                "id": f"0x{job.arb_id:X}",
                "data": job.data.hex().upper(),
                "interval_ms": int(job.interval_s * 1000),
            })

    def stop(self) -> None:
        if not self._running:
            return
        self._running = False
        if self._thread:
            self._thread.join(timeout=2.0)

        # periodic_stop 이벤트 출력
        for job in self._jobs:
            emit({
                "type": "periodic_stop",
                "bus": self._bus_label,
                "id": f"0x{job.arb_id:X}",
            })

    def _loop(self) -> None:
        try:
            while self._running:
                now = time.monotonic()
                for job in self._jobs:
                    if now >= job.next_send:
                        self._bus.send(job.msg)
                        job.next_send += job.interval_s
                time.sleep(0.001)  # 1ms tick
        except Exception as e:
            emit({
                "type": "error",
                "bus": self._bus_label,
                "code": PERIODIC_FAIL,
                "message": f"PeriodicManager crashed: {e}",
            })
            self._running = False
