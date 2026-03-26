"""monitor — 전체 버스 raw 캡처 (thread-safe 카운터 + rate 계산 + 실시간 경고)"""

from __future__ import annotations

import queue
import threading
import time

import click

from ..core.bus import open_bus
from ..core.errors import QUEUE_OVERFLOW
from ..core.jsonl import open_jsonl_writer
from ..core.message import CanFrame
from ..core.output import emit, emit_warning
from ..core.periodic import PeriodicManager


class _Stats:
    """Thread-safe 카운터."""

    def __init__(self):
        self._lock = threading.Lock()
        self.total = 0
        self.dropped = 0
        self._last_total = 0
        self._last_time = time.monotonic()

    def inc_total(self):
        with self._lock:
            self.total += 1

    def inc_dropped(self):
        with self._lock:
            self.dropped += 1

    def snapshot(self) -> dict:
        """현재 카운터 스냅샷 + rate 계산."""
        with self._lock:
            now = time.monotonic()
            dt = now - self._last_time
            rate = (self.total - self._last_total) / dt if dt > 0 else 0.0
            self._last_total = self.total
            self._last_time = now
            return {
                "total": self.total,
                "dropped": self.dropped,
                "rate_msg_s": round(rate, 1),
            }


# 실시간 overflow 경고 threshold
_OVERFLOW_WARN_INTERVAL = 5.0  # 초


def _recv_thread(bus, q: queue.Queue, overflow: str,
                 running: list, bus_label: str, stats: _Stats):
    """수신 스레드: python-can → queue. 의도된 drop 설계."""
    last_warn_time = 0.0

    while running[0]:
        try:
            msg = bus.recv(timeout=0.5)
        except Exception:
            break
        if msg is None:
            continue

        frame = CanFrame.from_can_message(msg, channel=bus_label)
        record = frame.to_record(bus=bus_label)

        if overflow == "drop":
            try:
                q.put_nowait(record)
            except queue.Full:
                stats.inc_dropped()
                _maybe_warn_overflow(stats, bus_label, last_warn_time)
        elif overflow == "block":
            q.put(record)
        else:  # ring — lock-free 스타일 ring buffer
            try:
                q.put_nowait(record)
            except queue.Full:
                try:
                    q.get_nowait()  # 오래된 프레임 제거
                except queue.Empty:
                    pass
                try:
                    q.put_nowait(record)
                except queue.Full:
                    pass
                stats.inc_dropped()
                now = time.monotonic()
                if now - last_warn_time >= _OVERFLOW_WARN_INTERVAL:
                    snap = stats.snapshot()
                    emit_warning(
                        QUEUE_OVERFLOW,
                        f"ring buffer overflow: {snap['dropped']} dropped, "
                        f"rate={snap['rate_msg_s']} msg/s",
                        bus=bus_label,
                        dropped=snap["dropped"],
                        rate=snap["rate_msg_s"],
                    )
                    last_warn_time = now


def _maybe_warn_overflow(stats: _Stats, bus_label: str,
                         last_warn_time: float):
    """drop 모드 실시간 overflow 경고."""
    now = time.monotonic()
    if now - last_warn_time >= _OVERFLOW_WARN_INTERVAL:
        snap = stats.snapshot()
        emit_warning(
            QUEUE_OVERFLOW,
            f"queue full: {snap['dropped']} dropped, "
            f"rate={snap['rate_msg_s']} msg/s",
            bus=bus_label,
            dropped=snap["dropped"],
            rate=snap["rate_msg_s"],
        )


def _writer_thread(q: queue.Queue, writer, running: list,
                   stats_interval: float, bus_label: str, stats: _Stats):
    """쓰기 스레드: queue → JSONL."""
    import json
    last_stats = time.monotonic()
    start_time = time.monotonic()

    while running[0] or not q.empty():
        try:
            record = q.get(timeout=0.5)
        except queue.Empty:
            if stats_interval > 0:
                now = time.monotonic()
                if now - last_stats >= stats_interval:
                    _emit_stats(stats, bus_label, start_time, writer)
                    last_stats = now
            continue

        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        writer.write(line + "\n")
        writer.flush()
        stats.inc_total()

        if stats_interval > 0:
            now = time.monotonic()
            if now - last_stats >= stats_interval:
                _emit_stats(stats, bus_label, start_time, writer)
                last_stats = now


def _emit_stats(stats: _Stats, bus_label: str,
                start_time: float, writer=None):
    """통계 출력."""
    snap = stats.snapshot()
    elapsed = round(time.monotonic() - start_time, 1)
    emit({
        "type": "stats",
        "bus": bus_label,
        "total": snap["total"],
        "dropped": snap["dropped"],
        "rate_msg_s": snap["rate_msg_s"],
        "elapsed": elapsed,
    }, file=writer)


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
@click.option("--fd", is_flag=True, default=False, help="CAN FD 모드")
@click.option("--data-bitrate", default=0, type=int, help="CAN FD 데이터 bps")
@click.option("--dry-run", is_flag=True, default=False)
def monitor(interface, channel, bitrate, output_path, duration,
            stats_interval, queue_size, overflow, requires_specs,
            fd, data_bitrate, dry_run):
    """전체 버스 raw 캡처."""
    periodic = PeriodicManager()
    if requires_specs:
        periodic.add_requires(list(requires_specs))

    writer = open_jsonl_writer(output_path)

    with open_bus(interface, channel, bitrate,
                  dry_run=dry_run, fd=fd,
                  data_bitrate=data_bitrate) as (bus, bus_label):
        periodic.start(bus, bus_label)

        q = queue.Queue(maxsize=queue_size)
        running = [True]
        stats = _Stats()

        recv_t = threading.Thread(
            target=_recv_thread,
            args=(bus, q, overflow, running, bus_label, stats),
            daemon=True,
        )
        write_t = threading.Thread(
            target=_writer_thread,
            args=(q, writer, running, stats_interval, bus_label, stats),
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

            snap = stats.snapshot()
            if snap["dropped"] > 0:
                emit_warning(
                    QUEUE_OVERFLOW,
                    f"total dropped: {snap['dropped']} frames",
                    bus=bus_label,
                    dropped=snap["dropped"],
                )

            elapsed = time.monotonic() - start_time
            emit({
                "type": "summary",
                "bus": bus_label,
                "total": snap["total"],
                "dropped": snap["dropped"],
                "elapsed": round(elapsed, 1),
            })

            if output_path and writer is not None:
                writer.close()
