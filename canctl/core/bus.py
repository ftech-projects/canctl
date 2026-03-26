"""Context Manager Bus 팩토리 — 모든 커맨드가 이 팩토리로만 Bus 오픈"""

from contextlib import contextmanager
from typing import Generator

import can

from .output import format_bus


class DryRunBus:
    """하드웨어 없이 로직 테스트용 더미 버스."""

    def __init__(self, interface: str = "dryrun", channel: str = "none"):
        self.channel_info = f"{interface}:{channel}"

    def send(self, msg: can.Message) -> None:
        pass  # 실제 송신 안 함

    def recv(self, timeout: float | None = None) -> can.Message | None:
        return None  # 항상 수신 없음

    def shutdown(self) -> None:
        pass

    def set_filters(self, filters=None) -> None:
        pass


@contextmanager
def open_bus(
    interface: str,
    channel: str,
    bitrate: int,
    dry_run: bool = False,
) -> Generator:
    """Bus Context Manager. Ctrl+C / 예외 시에도 shutdown 보장."""
    bus_label = format_bus(interface, channel)

    if dry_run:
        yield DryRunBus(interface, channel), bus_label
        return

    bus = can.Bus(interface=interface, channel=channel, bitrate=bitrate)
    try:
        yield bus, bus_label
    finally:
        bus.shutdown()
