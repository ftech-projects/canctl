"""recv — CAN 프레임 수신 (필터링 + 실시간 DBC 디코딩)"""

import time

import click

from ..core.bus import open_bus
from ..core.dbc import DbcDecoder
from ..core.errors import TIMEOUT
from ..core.output import emit, emit_error
from ..core.periodic import PeriodicManager


@click.command("recv")
@click.option("--interface", "-i", default="pcan")
@click.option("--channel", "-c", default="PCAN_USBBUS1")
@click.option("--bitrate", "-b", default=500000, type=int)
@click.option("--id", "filter_ids", multiple=True, required=True,
              help="필터 ID (hex), 복수 지정 가능")
@click.option("--mask", default="0x1FFFFFFF", help="필터 마스크")
@click.option("--count", "max_count", default=0, type=int,
              help="수신 후 종료 (0=무한)")
@click.option("--timeout", "timeout_s", default=0.0, type=float,
              help="타임아웃 초 (0=무한)")
@click.option("--dbc", "dbc_paths", multiple=True, help="DBC 경로")
@click.option("--requires", "requires_specs", multiple=True,
              help="주기 송신 'ID:DATA:INTERVALms'")
@click.option("--dry-run", is_flag=True, default=False)
def recv(interface, channel, bitrate, filter_ids, mask,
         max_count, timeout_s, dbc_paths, requires_specs, dry_run):
    """CAN 프레임 수신 (필터링 + DBC 디코딩)."""
    id_set = {int(x, 16) for x in filter_ids}
    mask_int = int(mask, 16)

    # DBC 디코더 준비
    decoder = DbcDecoder(dbc_paths) if dbc_paths else None

    # PeriodicManager 준비
    periodic = PeriodicManager()
    if requires_specs:
        periodic.add_requires(list(requires_specs))

    with open_bus(interface, channel, bitrate, dry_run=dry_run) as (bus, bus_label):
        # 하드웨어 필터 설정
        filters = [
            {"can_id": fid, "can_mask": mask_int, "extended": (fid > 0x7FF)}
            for fid in id_set
        ]
        bus.set_filters(filters)

        # 주기 송신 시작
        periodic.start(bus, bus_label)

        received = 0
        start_time = time.monotonic()
        timed_out = False

        try:
            while True:
                # 타임아웃 계산
                if timeout_s > 0:
                    elapsed = time.monotonic() - start_time
                    remaining = timeout_s - elapsed
                    if remaining <= 0:
                        timed_out = True
                        break
                    recv_timeout = min(remaining, 1.0)
                else:
                    recv_timeout = 1.0

                msg = bus.recv(timeout=recv_timeout)
                if msg is None:
                    continue

                # 소프트웨어 필터 (하드웨어 필터 미지원 드라이버 대비)
                if msg.arbitration_id not in id_set:
                    continue

                data_hex = msg.data.hex().upper()
                record = {
                    "type": "frame",
                    "bus": bus_label,
                    "id": f"0x{msg.arbitration_id:X}",
                    "ext": msg.is_extended_id,
                    "dlc": msg.dlc,
                    "data": data_hex,
                }

                # DBC 디코딩
                if decoder:
                    signals = decoder.try_decode_simple(
                        msg.arbitration_id, msg.data
                    )
                    if signals:
                        record["signals"] = signals

                emit(record)
                received += 1

                if max_count > 0 and received >= max_count:
                    break

        except KeyboardInterrupt:
            pass
        finally:
            periodic.stop()

        # 타임아웃 에러
        if timed_out and received == 0:
            emit_error(
                TIMEOUT,
                f"no frame received within {timeout_s}s",
                bus=bus_label,
            )

        elapsed = time.monotonic() - start_time
        emit({
            "type": "summary",
            "bus": bus_label,
            "received": received,
            "timeout": timed_out,
            "elapsed": round(elapsed, 3),
        })
