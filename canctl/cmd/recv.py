"""recv — CAN 프레임 수신 (queue 기반 + 필터링 + 실시간 DBC 디코딩)"""

from __future__ import annotations

import queue
import threading
import time

import click

from ..core.bus import open_bus
from ..core.dbc import DbcDecoder, CONFLICT_LATER_WINS
from ..core.errors import TIMEOUT
from ..core.filter import FilterManager
from ..core.message import CanFrame
from ..core.output import emit, emit_error
from ..core.periodic import PeriodicManager


def _recv_thread(bus, q: queue.Queue, fm: FilterManager,
                 running: list, bus_label: str):
    """수신 전용 스레드: bus.recv → SW 필터 → queue. 절대 블로킹 금지."""
    while running[0]:
        try:
            msg = bus.recv(timeout=0.5)
        except Exception:
            break
        if msg is None:
            continue
        # SW 필터 체크
        if not fm.match(msg.arbitration_id):
            continue
        frame = CanFrame.from_can_message(msg, channel=bus_label)
        try:
            q.put_nowait(frame)
        except queue.Full:
            pass  # drop — recv는 최신 프레임이 중요


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
@click.option("--dbc-priority", "dbc_priority", default="later",
              type=click.Choice(["later", "first", "error"]),
              help="DBC frame_id 충돌 정책")
@click.option("--requires", "requires_specs", multiple=True,
              help="주기 송신 'ID:DATA:INTERVALms'")
@click.option("--fd", is_flag=True, default=False, help="CAN FD 모드")
@click.option("--data-bitrate", default=0, type=int, help="CAN FD 데이터 bps")
@click.option("--dry-run", is_flag=True, default=False)
def recv(interface, channel, bitrate, filter_ids, mask,
         max_count, timeout_s, dbc_paths, dbc_priority,
         requires_specs, fd, data_bitrate, dry_run):
    """CAN 프레임 수신 (queue 기반 + 필터링 + DBC 디코딩)."""
    mask_int = int(mask, 16)

    # 필터 매니저
    fm = FilterManager(list(filter_ids), mask=mask_int)

    # DBC 디코더
    decoder = DbcDecoder(dbc_paths, conflict_policy=dbc_priority) \
        if dbc_paths else None

    # PeriodicManager
    periodic = PeriodicManager()
    if requires_specs:
        periodic.add_requires(list(requires_specs))

    with open_bus(interface, channel, bitrate,
                  dry_run=dry_run, fd=fd,
                  data_bitrate=data_bitrate) as (bus, bus_label):
        # HW 필터 설정
        fm.apply_hw_filter(bus)

        # 주기 송신 시작
        periodic.start(bus, bus_label)

        # 수신 queue + 스레드
        q: queue.Queue = queue.Queue(maxsize=5000)
        running = [True]
        recv_t = threading.Thread(
            target=_recv_thread,
            args=(bus, q, fm, running, bus_label),
            daemon=True,
        )
        recv_t.start()

        received = 0
        start_time = time.monotonic()
        timed_out = False

        try:
            while True:
                # 타임아웃 체크
                if timeout_s > 0:
                    elapsed = time.monotonic() - start_time
                    if elapsed >= timeout_s:
                        timed_out = True
                        break
                    wait_timeout = min(timeout_s - elapsed, 0.5)
                else:
                    wait_timeout = 0.5

                # queue에서 프레임 가져오기
                try:
                    frame = q.get(timeout=wait_timeout)
                except queue.Empty:
                    continue

                record = frame.to_record(bus=bus_label)

                # DBC 디코딩
                if decoder:
                    signals = decoder.try_decode_simple(
                        frame.arb_id, frame.data
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
            running[0] = False
            recv_t.join(timeout=2.0)
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
