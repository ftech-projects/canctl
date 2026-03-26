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


class TestBus:
    """bus.py 테스트"""

    def test_dry_run_bus(self):
        from canctl.core.bus import open_bus
        with open_bus("pcan", "PCAN_USBBUS1", 500000, dry_run=True) as (bus, label):
            assert label == "pcan:PCAN_USBBUS1"
            # send 호출해도 에러 없음
            import can
            msg = can.Message(arbitration_id=0x201, data=b"\x00" * 8)
            bus.send(msg)
            # recv는 None 반환
            assert bus.recv(timeout=0.01) is None

    def test_dry_run_shutdown(self):
        from canctl.core.bus import DryRunBus
        bus = DryRunBus()
        bus.shutdown()  # 에러 없어야 함


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

        # EngineRPM = 0x00C8 (200) * 0.1 = 20.0 rpm
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
        """dry-run 버스에서 PeriodicManager 시작/종료 테스트"""
        import time
        from canctl.core.periodic import PeriodicManager
        from canctl.core.bus import DryRunBus

        pm = PeriodicManager()
        pm.add_job(0x700, b"\x00", 100)

        bus = DryRunBus()
        pm.start(bus, "dryrun:none")
        time.sleep(0.3)  # 몇 번 송신되도록 대기
        pm.stop()
        # 에러 없이 종료되면 성공
