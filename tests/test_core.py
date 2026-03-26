"""core 모듈 단위 테스트"""

import json
import io
import os
import pytest

# 테스트 데이터 경로
TEST_DIR = os.path.dirname(__file__)
TEST_DBC = os.path.join(TEST_DIR, "test.dbc")
SAMPLE_JSONL = os.path.join(TEST_DIR, "sample_capture.jsonl")


class TestOutput:
    """output.py 테스트"""

    def test_emit_adds_ts_and_bus(self):
        from canctl.core.output import emit
        buf = io.StringIO()
        emit({"type": "test"}, file=buf)
        line = json.loads(buf.getvalue().strip())
        assert line["type"] == "test"
        assert "ts" in line
        assert "bus" in line

    def test_emit_preserves_existing_ts(self):
        from canctl.core.output import emit
        buf = io.StringIO()
        emit({"type": "test", "ts": 12345.0}, file=buf)
        line = json.loads(buf.getvalue().strip())
        assert line["ts"] == 12345.0

    def test_format_bus(self):
        from canctl.core.output import format_bus
        assert format_bus("pcan", "PCAN_USBBUS1") == "pcan:PCAN_USBBUS1"


class TestErrors:
    """errors.py 테스트"""

    def test_canctl_error(self):
        from canctl.core.errors import CanctlError, TIMEOUT
        err = CanctlError(TIMEOUT, "no frame")
        assert err.code == "TIMEOUT"
        assert err.message == "no frame"
        assert str(err) == "no frame"

    def test_new_error_codes_exist(self):
        """확장된 에러 코드 존재 확인"""
        from canctl.core import errors
        assert errors.BUS_OFF == "BUS_OFF"
        assert errors.ARB_LOST == "ARB_LOST"
        assert errors.DECODE_ERROR == "DECODE_ERROR"
        assert errors.INVALID_DBC == "INVALID_DBC"
        assert errors.SIGNAL_CONFLICT == "SIGNAL_CONFLICT"


class TestBus:
    """bus.py 테스트"""

    def test_dry_run_bus(self):
        from canctl.core.bus import open_bus
        with open_bus("pcan", "PCAN_USBBUS1", 500000, dry_run=True) as (bus, label):
            assert label == "pcan:PCAN_USBBUS1"
            import can
            msg = can.Message(arbitration_id=0x201, data=b"\x00" * 8)
            bus.send(msg)
            assert bus.recv(timeout=0.01) is None

    def test_dry_run_shutdown(self):
        from canctl.core.bus import DryRunBus
        bus = DryRunBus()
        bus.shutdown()

    def test_dry_run_send_periodic(self):
        """DryRunBus.send_periodic() 호환"""
        import can
        from canctl.core.bus import DryRunBus
        bus = DryRunBus()
        msg = can.Message(arbitration_id=0x700, data=b"\x00")
        task = bus.send_periodic(msg, 0.1)
        task.stop()  # 에러 없어야 함

    def test_virtual_bus(self):
        """VirtualBus — send → recv 루프백"""
        import can
        from canctl.core.bus import VirtualBus
        bus = VirtualBus()
        msg = can.Message(arbitration_id=0x201, data=b"\x01\x02")
        bus.send(msg)
        received = bus.recv(timeout=0.01)
        assert received is not None
        assert received.arbitration_id == 0x201
        assert received.data == b"\x01\x02"

    def test_virtual_bus_inject(self):
        """VirtualBus.inject() 외부 주입"""
        import can
        from canctl.core.bus import VirtualBus
        bus = VirtualBus()
        msg = can.Message(arbitration_id=0x300, data=b"\xFF")
        bus.inject(msg)
        received = bus.recv()
        assert received.arbitration_id == 0x300

    def test_virtual_bus_empty(self):
        from canctl.core.bus import VirtualBus
        bus = VirtualBus()
        assert bus.recv(timeout=0.01) is None

    def test_replay_bus(self):
        """ReplayBus — JSONL 레코드에서 프레임 재생"""
        from canctl.core.bus import ReplayBus
        records = [
            {"type": "frame", "id": "0x201", "data": "0102", "ext": False},
            {"type": "frame", "id": "0x202", "data": "AABB", "ext": False},
            {"type": "summary"},  # frame 아닌 것은 무시
        ]
        bus = ReplayBus(records)
        assert bus.remaining == 2

        msg1 = bus.recv()
        assert msg1.arbitration_id == 0x201
        msg2 = bus.recv()
        assert msg2.arbitration_id == 0x202
        assert bus.recv() is None
        assert bus.remaining == 0

    def test_open_bus_fd_params(self):
        """open_bus fd 파라미터 전달 확인 (dry_run)"""
        from canctl.core.bus import open_bus
        with open_bus("pcan", "PCAN_USBBUS1", 500000,
                      dry_run=True, fd=True, data_bitrate=2000000) as (bus, label):
            assert label == "pcan:PCAN_USBBUS1"


class TestJsonl:
    """jsonl.py 테스트"""

    def test_read_jsonl_file(self):
        from canctl.core.jsonl import read_jsonl
        records = list(read_jsonl(SAMPLE_JSONL))
        assert len(records) == 5
        assert records[0]["id"] == "0x201"
        assert records[1]["id"] == "0x202"

    def test_read_jsonl_missing_file(self):
        from canctl.core.jsonl import read_jsonl
        from canctl.core.errors import CanctlError
        with pytest.raises(CanctlError) as exc_info:
            list(read_jsonl("nonexistent.jsonl"))
        assert exc_info.value.code == "FILE_NOT_FOUND"


class TestDbc:
    """dbc.py 테스트"""

    def test_decode_engine_data(self):
        from canctl.core.dbc import DbcDecoder
        decoder = DbcDecoder([TEST_DBC])
        data = bytes.fromhex("C80000001E000000")
        result = decoder.decode(0x201, data)
        assert result is not None
        assert result["msg"] == "EngineData"
        assert "EngineRPM" in result["signals"]

    def test_decode_unknown_id(self):
        from canctl.core.dbc import DbcDecoder
        decoder = DbcDecoder([TEST_DBC])
        result = decoder.decode(0x999, b"\x00" * 8)
        assert result is None

    def test_try_decode_simple(self):
        from canctl.core.dbc import DbcDecoder
        decoder = DbcDecoder([TEST_DBC])
        data = bytes.fromhex("C80000001E000000")
        signals = decoder.try_decode_simple(0x201, data)
        assert signals is not None
        assert "EngineRPM" in signals

    def test_bad_dbc_path(self):
        from canctl.core.dbc import DbcDecoder
        from canctl.core.errors import CanctlError
        with pytest.raises(CanctlError) as exc_info:
            DbcDecoder(["nonexistent.dbc"])
        assert exc_info.value.code == "DBC_PARSE_FAIL"

    def test_conflict_later_wins(self):
        """같은 DBC 2번 로드 — later wins (기본)"""
        from canctl.core.dbc import DbcDecoder
        decoder = DbcDecoder([TEST_DBC, TEST_DBC], conflict_policy="later")
        assert len(decoder.conflicts) > 0
        # 디코딩은 정상 동작해야 함
        data = bytes.fromhex("C80000001E000000")
        result = decoder.decode(0x201, data)
        assert result is not None

    def test_conflict_error_policy(self):
        """error 정책 — 중복 시 에러"""
        from canctl.core.dbc import DbcDecoder
        from canctl.core.errors import CanctlError
        with pytest.raises(CanctlError) as exc_info:
            DbcDecoder([TEST_DBC, TEST_DBC], conflict_policy="error")
        assert exc_info.value.code == "SIGNAL_CONFLICT"


class TestPeriodic:
    """periodic.py 테스트"""

    def test_parse_requires_valid(self):
        from canctl.core.periodic import parse_requires
        result = parse_requires("0x700:00:100ms")
        assert result["id"] == 0x700
        assert result["data"] == b"\x00"
        assert result["interval_s"] == 0.1

    def test_parse_requires_invalid(self):
        from canctl.core.periodic import parse_requires
        from canctl.core.errors import CanctlError
        with pytest.raises(CanctlError) as exc_info:
            parse_requires("bad_format")
        assert exc_info.value.code == "INVALID_ARG"

    def test_periodic_manager_dry_run(self):
        """dry-run 버스에서 PeriodicManager 시작/종료"""
        import time
        from canctl.core.periodic import PeriodicManager
        from canctl.core.bus import DryRunBus

        pm = PeriodicManager()
        pm.add_job(0x700, b"\x00", 100)

        bus = DryRunBus()
        pm.start(bus, "dryrun:none")
        time.sleep(0.3)
        pm.stop()

    def test_periodic_manager_virtual_bus(self):
        """VirtualBus에서 실제 주기 송신 확인"""
        import time
        from canctl.core.periodic import PeriodicManager
        from canctl.core.bus import VirtualBus

        pm = PeriodicManager()
        pm.add_job(0x700, b"\x00", 50)  # 50ms 주기

        bus = VirtualBus()
        pm.start(bus, "virtual:test")
        time.sleep(0.3)  # ~6 프레임
        pm.stop()

        # VirtualBus에 프레임이 쌓여야 함
        count = 0
        while bus.recv(timeout=0.001) is not None:
            count += 1
        assert count >= 3  # 최소 3 프레임


class TestMessage:
    """message.py 테스트"""

    def test_can_frame_basic(self):
        from canctl.core.message import CanFrame
        frame = CanFrame(arb_id=0x201, data=b"\x01\x02\x03")
        assert frame.dlc == 3
        assert frame.id_hex == "0x201"
        assert frame.data_hex == "010203"
        assert frame.is_extended is False
        assert frame.is_fd is False

    def test_can_frame_ts(self):
        from canctl.core.message import CanFrame
        frame = CanFrame(arb_id=0x201, data=b"\x00",
                         ts_ns=1_710_000_000_123_456_789)
        assert abs(frame.ts - 1710000000.123456789) < 0.001

    def test_can_frame_to_record(self):
        from canctl.core.message import CanFrame
        frame = CanFrame(arb_id=0x201, data=b"\xAA\xBB",
                         is_fd=True)
        record = frame.to_record(bus="pcan:PCAN_USBBUS1")
        assert record["type"] == "frame"
        assert record["id"] == "0x201"
        assert record["data"] == "AABB"
        assert record["fd"] is True
        assert record["bus"] == "pcan:PCAN_USBBUS1"

    def test_can_frame_from_record(self):
        from canctl.core.message import CanFrame
        record = {
            "id": "0x202",
            "data": "FFEE",
            "ext": True,
            "fd": True,
            "dlc": 2,
            "ts": 1710000000.5,
        }
        frame = CanFrame.from_record(record)
        assert frame.arb_id == 0x202
        assert frame.data == b"\xFF\xEE"
        assert frame.is_extended is True
        assert frame.is_fd is True

    def test_can_frame_from_can_message(self):
        import can
        from canctl.core.message import CanFrame
        msg = can.Message(
            arbitration_id=0x201,
            data=b"\x01\x02\x03",
            is_extended_id=False,
        )
        frame = CanFrame.from_can_message(msg, channel="test")
        assert frame.arb_id == 0x201
        assert frame.channel == "test"


class TestFilter:
    """filter.py 테스트"""

    def test_filter_manager_basic(self):
        from canctl.core.filter import FilterManager
        fm = FilterManager(["0x201", "0x202"])
        assert fm.match(0x201) is True
        assert fm.match(0x202) is True
        assert fm.match(0x999) is False

    def test_filter_manager_empty(self):
        """빈 필터 → 모든 ID 통과"""
        from canctl.core.filter import FilterManager
        fm = FilterManager([])
        assert fm.is_empty is True
        assert fm.match(0x201) is True

    def test_filter_hw_apply(self):
        """HW 필터 적용 (DryRunBus)"""
        from canctl.core.filter import FilterManager
        from canctl.core.bus import DryRunBus
        fm = FilterManager(["0x201"])
        bus = DryRunBus()
        result = fm.apply_hw_filter(bus)
        assert result is True

    def test_filter_to_dict(self):
        from canctl.core.filter import FilterManager
        fm = FilterManager(["0x201"])
        dicts = fm.to_dict_list()
        assert len(dicts) == 1
        assert dicts[0]["id"] == "0x201"

    def test_filter_extended_auto_detect(self):
        """0x7FF 초과 → extended 자동 감지"""
        from canctl.core.filter import CanFilter
        f = CanFilter.from_id("0x18FF50E5")
        assert f.extended is True
        f2 = CanFilter.from_id("0x201")
        assert f2.extended is False
