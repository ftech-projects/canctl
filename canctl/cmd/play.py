"""play — 캡처된 JSONL 파일을 타임스탬프 기준으로 재생 (jitter, burst 지원)"""

from __future__ import annotations

import random
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
@click.option("--jitter", "jitter_ms", default=0.0, type=float,
              help="각 프레임에 ±jitter ms 랜덤 지연 추가")
@click.option("--burst", "burst_count", default=1, type=int,
              help="각 프레임을 N번 burst 송신 (기본 1)")
@click.option("--fd", is_flag=True, default=False, help="CAN FD 모드")
@click.option("--data-bitrate", default=0, type=int, help="CAN FD 데이터 bps")
@click.option("--dry-run", is_flag=True, default=False)
def play(input_file, interface, channel, bitrate, speed, loop,
         jitter_ms, burst_count, fd, data_bitrate, dry_run):
    """캡처된 JSONL 파일을 타임스탬프 기준으로 재생."""
    jitter_s = jitter_ms / 1000.0
    burst_count = max(1, burst_count)

    with open_bus(interface, channel, bitrate,
                  dry_run=dry_run, fd=fd,
                  data_bitrate=data_bitrate) as (bus, bus_label):
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
                        # jitter 적용
                        if jitter_s > 0:
                            delay += random.uniform(-jitter_s, jitter_s)
                        if delay > 0:
                            time.sleep(delay)
                    prev_ts = ts

                    # 프레임 구성
                    id_str = record.get("id", "0x0")
                    arb_id = int(id_str, 16)
                    data = bytes.fromhex(record.get("data", ""))

                    msg = can.Message(
                        arbitration_id=arb_id,
                        data=data,
                        is_extended_id=record.get("ext", False),
                        is_fd=record.get("fd", False),
                    )

                    # burst 송신
                    for _ in range(burst_count):
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
