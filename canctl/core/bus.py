"""Context Manager Bus 팩토리 — 모든 커맨드가 이 팩토리로만 Bus 오픈"""

from __future__ import annotations

import collections
import time
from contextlib import contextmanager
from typing import Generator

import can

from .output import format_bus


# ---------------------------------------------------------------------------
# DryRunBus — 하드웨어 없이 로직 테스트용
# ---------------------------------------------------------------------------

class DryRunBus:
    """하드웨어 없이 로직 테스트용 더미 버스."""

    def __init__(self, interface: str = "dryrun", channel: str = "none"):
        self.channel_info = f"{interface}:{channel}"

    def send(self, msg: can.Message) -> None:
        pass

    def recv(self, timeout: float | None = None) -> can.Message | None:
        return None

    def shutdown(self) -> None:
        pass

    def set_filters(self, filters=None) -> None:
        pass

    def send_periodic(self, msgs, period, duration=None):
        """python-can 호환 — dry-run에서는 아무것도 안 함."""
        return _DummyTask()


class _DummyTask:
    """send_periodic 반환용 더미 태스크."""
    def stop(self):
        pass


# ---------------------------------------------------------------------------
# VirtualBus — 테스트 자동화용 (send → 내부 큐 → recv)
# ---------------------------------------------------------------------------

class VirtualBus:
    """send한 프레임을 recv로 되돌려 받는 가상 버스. LLM 테스트 자동화용.

    send_periodic 미지원 → PeriodicManager가 SW thread fallback 사용.
    """

    def __init__(self, channel: str = "virtual0"):
        self.channel_info = f"virtual:{channel}"
        self._queue: collections.deque = collections.deque(maxlen=10000)

    def send(self, msg: can.Message) -> None:
        self._queue.append(msg)

    def recv(self, timeout: float | None = None) -> can.Message | None:
        if self._queue:
            return self._queue.popleft()
        if timeout and timeout > 0:
            time.sleep(min(timeout, 0.01))
        return None

    def shutdown(self) -> None:
        self._queue.clear()

    def set_filters(self, filters=None) -> None:
        pass

    def inject(self, msg: can.Message) -> None:
        """외부에서 수신 프레임 주입 (테스트용)."""
        self._queue.append(msg)


# ---------------------------------------------------------------------------
# ReplayBus — JSONL 캡처 파일에서 프레임을 순서대로 수신
# ---------------------------------------------------------------------------

class ReplayBus:
    """JSONL 캡처 파일을 읽어 recv()로 프레임을 재공급하는 버스."""

    def __init__(self, records: list[dict], channel: str = "replay"):
        self.channel_info = f"replay:{channel}"
        self._frames: list[can.Message] = []
        self._index = 0
        for rec in records:
            if rec.get("type") != "frame":
                continue
            arb_id = int(rec.get("id", "0x0"), 16)
            data = bytes.fromhex(rec.get("data", ""))
            self._frames.append(can.Message(
                arbitration_id=arb_id,
                data=data,
                is_extended_id=rec.get("ext", False),
                is_fd=rec.get("fd", False),
            ))

    def send(self, msg: can.Message) -> None:
        pass

    def recv(self, timeout: float | None = None) -> can.Message | None:
        if self._index < len(self._frames):
            msg = self._frames[self._index]
            self._index += 1
            return msg
        return None

    def shutdown(self) -> None:
        self._index = 0

    def set_filters(self, filters=None) -> None:
        pass

    @property
    def remaining(self) -> int:
        return len(self._frames) - self._index

    def send_periodic(self, msgs, period, duration=None):
        return _DummyTask()


# ---------------------------------------------------------------------------
# open_bus — Context Manager 팩토리
# ---------------------------------------------------------------------------

@contextmanager
def open_bus(
    interface: str,
    channel: str,
    bitrate: int,
    dry_run: bool = False,
    fd: bool = False,
    data_bitrate: int = 0,
) -> Generator:
    """Bus Context Manager. Ctrl+C / 예외 시에도 shutdown 보장.

    Args:
        fd: CAN FD 모드 활성화
        data_bitrate: CAN FD 데이터 비트레이트 (0이면 bitrate과 동일)
    """
    bus_label = format_bus(interface, channel)

    if dry_run:
        yield DryRunBus(interface, channel), bus_label
        return

    kwargs = {
        "interface": interface,
        "channel": channel,
        "bitrate": bitrate,
    }
    if fd:
        kwargs["fd"] = True
        kwargs["data_bitrate"] = data_bitrate or bitrate

    bus = can.Bus(**kwargs)
    try:
        yield bus, bus_label
    finally:
        bus.shutdown()
