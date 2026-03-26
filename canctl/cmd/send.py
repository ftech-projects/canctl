"""send — CAN 프레임 송신 (단발 or 반복, CAN FD 지원)"""

import time

import can
import click

from ..core.bus import open_bus
from ..core.errors import SEND_FAIL
from ..core.output import emit, emit_error


def _parse_hex_data(data_str: str) -> bytes:
    """'01 02 03' 또는 '010203' → bytes"""
    cleaned = data_str.replace(" ", "")
    return bytes.fromhex(cleaned)


@click.command("send")
@click.option("--interface", "-i", default="pcan", help="pcan / vector / kvaser")
@click.option("--channel", "-c", default="PCAN_USBBUS1", help="채널명")
@click.option("--bitrate", "-b", default=500000, type=int, help="bps")
@click.option("--id", "arb_id", required=True, help="CAN ID (hex, 예: 0x18FF50E5)")
@click.option("--ext", is_flag=True, default=False, help="Extended 29-bit ID")
@click.option("--data", "data_str", required=True, help="hex 바이트 (공백 구분 가능)")
@click.option("--repeat", default=1, type=int, help="반복 횟수 (0=무한)")
@click.option("--interval", default=0.0, type=float, help="반복 간격 초")
@click.option("--fd", is_flag=True, default=False, help="CAN FD 모드")
@click.option("--data-bitrate", default=0, type=int, help="CAN FD 데이터 bps")
@click.option("--dry-run", is_flag=True, default=False, help="실제 송신 안 함")
def send(interface, channel, bitrate, arb_id, ext, data_str,
         repeat, interval, fd, data_bitrate, dry_run):
    """CAN 프레임 송신."""
    arb_id_int = int(arb_id, 16)
    data = _parse_hex_data(data_str)

    with open_bus(interface, channel, bitrate,
                  dry_run=dry_run, fd=fd,
                  data_bitrate=data_bitrate) as (bus, bus_label):
        msg = can.Message(
            arbitration_id=arb_id_int,
            data=data,
            is_extended_id=ext,
            is_fd=fd,
        )

        count = 0
        infinite = (repeat == 0)
        try:
            while infinite or count < repeat:
                try:
                    bus.send(msg)
                    record = {
                        "type": "send",
                        "bus": bus_label,
                        "id": f"0x{arb_id_int:X}",
                        "ext": ext,
                        "dlc": len(data),
                        "data": data.hex().upper(),
                        "status": "ok",
                    }
                    if fd:
                        record["fd"] = True
                    emit(record)
                except Exception as e:
                    emit_error(SEND_FAIL, str(e), bus=bus_label)
                    return

                count += 1
                if (infinite or count < repeat) and interval > 0:
                    time.sleep(interval)
        except KeyboardInterrupt:
            pass

        emit({
            "type": "summary",
            "bus": bus_label,
            "sent": count,
        })
