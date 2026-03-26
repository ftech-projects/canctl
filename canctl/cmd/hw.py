"""hw list — 사용 가능한 CAN 인터페이스 열거"""

import click

from ..core.output import emit

# python-can에서 지원하는 주요 인터페이스
_INTERFACES = [
    ("pcan", "PCAN_USBBUS1"),
    ("pcan", "PCAN_USBBUS2"),
    ("vector", "0"),
    ("vector", "1"),
    ("kvaser", "0"),
    ("kvaser", "1"),
]


def _probe_interface(interface: str, channel: str) -> str:
    """인터페이스 상태 확인. 실제 연결 시도 없이 드라이버 존재 여부만 확인."""
    try:
        import can
        # 짧은 timeout으로 bus 열어서 확인
        bus = can.Bus(interface=interface, channel=channel, bitrate=500000)
        bus.shutdown()
        return "available"
    except Exception:
        return "unavailable"


@click.command("list")
@click.option("--probe", is_flag=True, default=False,
              help="실제 드라이버 연결 시도 (느림)")
def hw_list(probe: bool):
    """사용 가능한 CAN 인터페이스 열거."""
    for interface, channel in _INTERFACES:
        state = "unknown"
        if probe:
            state = _probe_interface(interface, channel)
        emit({
            "type": "hw",
            "bus": None,
            "interface": interface,
            "channel": channel,
            "state": state,
        })


@click.group("hw")
def hw():
    """CAN 하드웨어 관리."""
    pass


hw.add_command(hw_list)
