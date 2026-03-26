"""monitor — 전체 버스 raw 캡처 (실시간 파싱 없음)"""

import queue
import threading
import time

import click

from ..core.bus import open_bus
from ..core.errors import QUEUE_OVERFLOW
from ..core.jsonl import open_jsonl_writer
from ..core.output import emit, emit_warning
from ..core.periodic import PeriodicManager


def _recv_thread(bus, q: queue.Queue, overflow: str, running: list,
                 bus_label: str, drop_count: list):
    """수신 스레드: python-can → queue"""
    while running[0]:
        try:
            msg = bus.recv(timeout=0.5)
        except Exception:
            break
        if msg is None:
            continue

        record = {
            "type": "frame",
            "ts": time.time(),
            "bus": bus_label,
            "id": f"0x{msg.arbitration_id:X}",
            "ext": msg.is_extended_id,
            "dlc": msg.dlc,
            "data": msg.data.hex().upper(),
        }

        if overflow == "drop":
            try:
                q.put_nowait(record)
            except queue.Full:
                drop_count[0] += 1
        elif overflow == "block":
            q.put(record)
        else:  # ring
            try:
                q.put_nowait(record)
            except queue.Full:
                try:
                    q.get_nowait()  # 오래된 프레임 제거
                except queue.Empty:
                    pass
                q.put_nowait(record)
                drop_count[0] += 1


def _writer_thread(q: queue.Queue, writer, running: list,
                   stats_interval: float, bus_label: str,
                   total_count: list, drop_count: list):
    """쓰기 스레드: queue → JSONL"""
    import json
    last_stats = time.monotonic()
    start_time = time.monotonic()

    while running[0] or not q.empty():
        try:
            record = q.get(timeout=0.5)
        except queue.Empty:
            # 통계 출력 체크
            if stats_interval > 0:
                now = time.monotonic()
                if now - last_stats >= stats_interval:
                    emit({
                        "type": "stats",
                        "bus": bus_label,
                        "total": total_count[0],
                        "dropped": drop_count[0],
                        "elapsed": round(now - start_time, 1),
                    }, file=writer)
                    last_stats = now
            continue

        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        writer.write(line + "\n")
        writer.flush()
        total_count[0] += 1

        # 통계 출력
        if stats_interval > 0:
            now = time.monotonic()
            if now - last_stats >= stats_interval:
                emit({
                    "type": "stats",
                    "bus": bus_label,
                    "total": total_count[0],
                    "dropped": drop_count[0],
                    "elapsed": round(now - start_time, 1),
                }, file=writer)
                last_stats = now


@click.command("monitor")
@click.option("--interface", "-i", default="pcan")
@click.option("--channel", "-c", default="PCAN_USBBUS1")
@click.option("--bitrate", "-b", default=500000, type=int)
@click.option("--output", "-o", "output_path", default=None,
              help="JSONL 저장 경로 (기본: stdout)")
@click.option("--duration", default=0.0, type=float, help="캡처 시간 초")
@click.option("--stats-interval", default=0.0, type=float, help="통계 출력 주기 초")
@click.option("--queue-size", default=10000, type=int, help="내부 큐 크기")
@click.option("--overflow", default="ring",
              type=click.Choice(["drop", "block", "ring"]))
@click.option("--requires", "requires_specs", multiple=True,
              help="주기 송신 'ID:DATA:INTERVALms'")
@click.option("--dry-run", is_flag=True, default=False)
def monitor(interface, channel, bitrate, output_path, duration,
            stats_interval, queue_size, overflow, requires_specs, dry_run):
    """전체 버스 raw 캡처."""
    periodic = PeriodicManager()
    if requires_specs:
        periodic.add_requires(list(requires_specs))

    writer = open_jsonl_writer(output_path)

    with open_bus(interface, channel, bitrate, dry_run=dry_run) as (bus, bus_label):
        periodic.start(bus, bus_label)

        q = queue.Queue(maxsize=queue_size)
        running = [True]
        total_count = [0]
        drop_count = [0]

        recv_t = threading.Thread(
            target=_recv_thread,
            args=(bus, q, overflow, running, bus_label, drop_count),
            daemon=True,
        )
        write_t = threading.Thread(
            target=_writer_thread,
            args=(q, writer, running, stats_interval, bus_label,
                  total_count, drop_count),
            daemon=True,
        )

        recv_t.start()
        write_t.start()

        start_time = time.monotonic()
        try:
            while True:
                time.sleep(0.1)
                if duration > 0:
                    if time.monotonic() - start_time >= duration:
                        break
        except KeyboardInterrupt:
            pass
        finally:
            running[0] = False
            recv_t.join(timeout=3.0)
            write_t.join(timeout=3.0)
            periodic.stop()

            if drop_count[0] > 0:
                emit_warning(
                    QUEUE_OVERFLOW,
                    f"ring buffer dropped {drop_count[0]} frames",
                    bus=bus_label,
                    dropped=drop_count[0],
                )

            elapsed = time.monotonic() - start_time
            emit({
                "type": "summary",
                "bus": bus_label,
                "total": total_count[0],
                "dropped": drop_count[0],
                "elapsed": round(elapsed, 1),
            })

            if output_path and writer is not None:
                writer.close()
