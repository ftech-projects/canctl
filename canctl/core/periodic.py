"""PeriodicManager — bus.send_periodic() 우선, fallback: job별 독립 스레드"""

from __future__ import annotations

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


class _JobThread(threading.Thread):
    """개별 job 전용 독립 스레드 (fallback 모드)."""

    def __init__(self, job: _Job, bus, bus_label: str):
        super().__init__(daemon=True, name=f"periodic-0x{job.arb_id:X}")
        self._job = job
        self._bus = bus
        self._bus_label = bus_label
        self._running = True

    def run(self):
        job = self._job
        try:
            next_send = time.monotonic()
            while self._running:
                now = time.monotonic()
                if now >= next_send:
                    self._bus.send(job.msg)
                    next_send += job.interval_s
                    # drift 보정 — 밀린 경우 건너뛰기
                    if next_send < now:
                        next_send = now + job.interval_s
                # 남은 시간만큼 sleep (최소 0.5ms)
                sleep_time = max(next_send - time.monotonic(), 0.0005)
                time.sleep(sleep_time)
        except Exception as e:
            emit({
                "type": "error",
                "bus": self._bus_label,
                "code": PERIODIC_FAIL,
                "message": f"periodic 0x{job.arb_id:X} crashed: {e}",
            })

    def stop(self):
        self._running = False


class PeriodicManager:
    """주기 송신 관리.

    전략:
    1. bus.send_periodic() 시도 (드라이버 레벨 타이머, PCAN HW 타이머 등)
    2. 실패 시 job별 독립 스레드로 fallback
    """

    def __init__(self):
        self._jobs: list[_Job] = []
        self._bus = None
        self._bus_label: str | None = None
        self._hw_tasks: list = []        # send_periodic 반환 태스크
        self._sw_threads: list[_JobThread] = []  # fallback 스레드
        self._using_hw = False

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

        # 전략 1: bus.send_periodic() 시도
        if self._try_hw_periodic():
            self._using_hw = True
        else:
            # 전략 2: job별 독립 스레드
            self._start_sw_threads()
            self._using_hw = False

        # periodic_start 이벤트 출력
        mode = "hw" if self._using_hw else "sw"
        for job in self._jobs:
            emit({
                "type": "periodic_start",
                "bus": bus_label,
                "id": f"0x{job.arb_id:X}",
                "data": job.data.hex().upper(),
                "interval_ms": int(job.interval_s * 1000),
                "mode": mode,
            })

    def _try_hw_periodic(self) -> bool:
        """bus.send_periodic()으로 HW 타이머 시도. 실패 시 False."""
        if not hasattr(self._bus, "send_periodic"):
            return False
        try:
            for job in self._jobs:
                task = self._bus.send_periodic(
                    job.msg, job.interval_s
                )
                self._hw_tasks.append(task)
            return True
        except (NotImplementedError, AttributeError, Exception):
            # HW periodic 미지원 → 이미 생성된 task 정리
            for task in self._hw_tasks:
                try:
                    task.stop()
                except Exception:
                    pass
            self._hw_tasks.clear()
            return False

    def _start_sw_threads(self) -> None:
        """job별 독립 스레드 시작."""
        for job in self._jobs:
            t = _JobThread(job, self._bus, self._bus_label)
            t.start()
            self._sw_threads.append(t)

    def stop(self) -> None:
        # HW 태스크 정지
        for task in self._hw_tasks:
            try:
                task.stop()
            except Exception:
                pass
        self._hw_tasks.clear()

        # SW 스레드 정지
        for t in self._sw_threads:
            t.stop()
        for t in self._sw_threads:
            t.join(timeout=2.0)
        self._sw_threads.clear()

        # periodic_stop 이벤트 출력
        for job in self._jobs:
            emit({
                "type": "periodic_stop",
                "bus": self._bus_label,
                "id": f"0x{job.arb_id:X}",
            })
