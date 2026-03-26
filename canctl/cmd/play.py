"""play — 캡처된 JSONL 파일을 타임스탬프 기준으로 재생"""

import time

import can
import click

from ..core.bus import open_bus
from ..core.errors import SEND_FAIL
from ..core.jsonl import read_jsonl
from ..core.output import emit, emit_error


@click.command("play")
@click.argument("input_file")
@click.option("--interface", "-i", default="pcan")
@click.option("--channel", "-c", default="PCAN_USBBUS1")
@click.option("--bitrate", "-b", default=500000, type=int)
@click.option("--speed", default=1.0, type=float,
              help="재생 배속 (0=즉시)")
@click.option("--loop", is_flag=True, default=False, help="반복 재생")
@click.option("--dry-run", is_flag=True, default=False)
def play(input_file, interface, channel, bitrate, speed, loop, dry_run):
    """캡처된 JSONL 파일을 타임스탬프 기준으로 재생."""
    with open_bus(interface, channel, bitrate, dry_run=dry_run) as (bus, bus_label):
        played = 0
        start_time = time.monotonic()

        try:
            while True:
                prev_ts = None
                for record in read_jsonl(input_file):
                    if record.get("type") != "frame":
                        continue

                    # 타임스탬프 기반 딜레이
                    ts = record.get("ts")
                    if ts is not None and prev_ts is not None and speed > 0:
                        delay = (ts - prev_ts) / speed
                        if delay > 0:
                            time.sleep(delay)
                    prev_ts = ts

                    # 프레임 송신
                    id_str = record.get("id", "0x0")
                    arb_id = int(id_str, 16)
                    data = bytes.fromhex(record.get("data", ""))

                    msg = can.Message(
                        arbitration_id=arb_id,
                        data=data,
                        is_extended_id=record.get("ext", False),
                    )

                    try:
                        bus.send(msg)
                        emit({
                            "type": "play",
                            "bus": bus_label,
                            "id": id_str,
                            "data": record.get("data", ""),
                            "status": "sent",
                        })
                        played += 1
                    except Exception as e:
                        emit_error(SEND_FAIL, str(e), bus=bus_label)

                if not loop:
                    break

        except KeyboardInterrupt:
            pass

        elapsed = time.monotonic() - start_time
        emit({
            "type": "summary",
            "bus": bus_label,
            "played": played,
            "elapsed": round(elapsed, 3),
        })
