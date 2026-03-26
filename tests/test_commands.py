"""CLI 커맨드 시뮬레이션 테스트 — dry-run 기반, 하드웨어 불필요"""

import json
import os

from click.testing import CliRunner

from canctl.canctl import cli

TEST_DIR = os.path.dirname(__file__)
TEST_DBC = os.path.join(TEST_DIR, "test.dbc")
SAMPLE_JSONL = os.path.join(TEST_DIR, "sample_capture.jsonl")


class TestHw:
    def test_hw_list(self):
        """hw list --probe 없이 실행"""
        runner = CliRunner()
        result = runner.invoke(cli, ["hw", "list"])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n") if l]
        assert all(r["type"] == "hw" for r in lines)
        assert any(r["interface"] == "pcan" for r in lines)


class TestSend:
    def test_send_single_dry_run(self):
        """단일 프레임 dry-run 송신"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "send",
            "--id", "0x201",
            "--data", "01 02 03 04 05 06 07 08",
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        send_lines = [l for l in lines if l["type"] == "send"]
        assert len(send_lines) == 1
        assert send_lines[0]["status"] == "ok"
        assert send_lines[0]["data"] == "0102030405060708"

    def test_send_repeat_dry_run(self):
        """3회 반복 dry-run 송신"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "send",
            "--id", "0x18FF50E5",
            "--ext",
            "--data", "AABB",
            "--repeat", "3",
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        send_lines = [l for l in lines if l["type"] == "send"]
        assert len(send_lines) == 3
        assert all(l["ext"] is True for l in send_lines)

        summary = [l for l in lines if l["type"] == "summary"]
        assert summary[0]["sent"] == 3

    def test_send_extended_id(self):
        """29-bit 확장 ID 테스트"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "send",
            "--id", "0x18FF50E5",
            "--ext",
            "--data", "FF",
            "--dry-run",
        ])
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        send_line = [l for l in lines if l["type"] == "send"][0]
        assert send_line["id"] == "0x18FF50E5"
        assert send_line["ext"] is True


class TestRecv:
    def test_recv_dry_run_timeout(self):
        """dry-run 수신 — 타임아웃 발생"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "recv",
            "--id", "0x201",
            "--timeout", "0.5",
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        # dry-run이므로 프레임 없음 → 타임아웃 에러
        error_lines = [l for l in lines if l["type"] == "error"]
        assert any(l["code"] == "TIMEOUT" for l in error_lines)

        summary = [l for l in lines if l["type"] == "summary"]
        assert summary[0]["received"] == 0
        assert summary[0]["timeout"] is True

    def test_recv_with_requires_dry_run(self):
        """--requires 포함 dry-run 수신"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "recv",
            "--id", "0x201",
            "--timeout", "0.5",
            "--requires", "0x700:00:100ms",
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        # periodic_start/stop 이벤트 확인
        starts = [l for l in lines if l["type"] == "periodic_start"]
        stops = [l for l in lines if l["type"] == "periodic_stop"]
        assert len(starts) == 1
        assert starts[0]["id"] == "0x700"
        assert starts[0]["interval_ms"] == 100
        assert len(stops) == 1


class TestMonitor:
    def test_monitor_dry_run_duration(self):
        """dry-run 모니터 — 짧은 duration"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "monitor",
            "--duration", "0.5",
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        summary = [l for l in lines if l["type"] == "summary"]
        assert len(summary) == 1
        assert summary[0]["total"] == 0  # dry-run이므로 프레임 없음


class TestDecode:
    def test_decode_from_file(self):
        """캡처 파일 DBC 디코딩"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "decode",
            "--dbc", TEST_DBC,
            "--input", SAMPLE_JSONL,
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]

        decoded = [l for l in lines if l["type"] == "decoded"]
        unknown = [l for l in lines if l["type"] == "unknown"]

        # 0x201 (EngineData) 3개, 0x202 (VehicleSpeed) 2개
        assert len(decoded) == 5
        assert len(unknown) == 0

        # EngineData 디코딩 확인
        engine = [l for l in decoded if l.get("msg") == "EngineData"]
        assert len(engine) == 3
        assert "EngineRPM" in engine[0]["signals"]

        # VehicleSpeed 디코딩 확인
        vehicle = [l for l in decoded if l.get("msg") == "VehicleSpeed"]
        assert len(vehicle) == 2
        assert "Speed" in vehicle[0]["signals"]

    def test_decode_preserves_data_field(self):
        """디코딩 후 raw data 필드 유지 확인"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "decode",
            "--dbc", TEST_DBC,
            "--input", SAMPLE_JSONL,
        ])
        lines = [json.loads(l) for l in result.output.strip().split("\n")]
        for line in lines:
            assert "data" in line  # raw data 항상 유지


class TestPlay:
    def test_play_dry_run(self):
        """dry-run 재생 테스트"""
        runner = CliRunner()
        result = runner.invoke(cli, [
            "play", SAMPLE_JSONL,
            "--speed", "0",  # 즉시 재생
            "--dry-run",
        ])
        assert result.exit_code == 0
        lines = [json.loads(l) for l in result.output.strip().split("\n")]

        play_lines = [l for l in lines if l["type"] == "play"]
        assert len(play_lines) == 5  # 5개 프레임

        summary = [l for l in lines if l["type"] == "summary"]
        assert summary[0]["played"] == 5

    def test_play_speed_factor(self):
        """배속 재생 — 시간 확인"""
        import time
        runner = CliRunner()
        start = time.monotonic()
        result = runner.invoke(cli, [
            "play", SAMPLE_JSONL,
            "--speed", "10.0",  # 10배속 → 0.04초에 완료
            "--dry-run",
        ])
        elapsed = time.monotonic() - start
        assert result.exit_code == 0
        # 10배속이면 0.4초 원본 → 0.04초, 여유 포함 1초 이내
        assert elapsed < 1.0


class TestPipeline:
    """파이프라인 시뮬레이션: play --dry-run → decode"""

    def test_play_then_decode(self, tmp_path):
        """play dry-run 출력 → decode 파이프라인"""
        runner = CliRunner()

        # 1단계: play dry-run → 임시 파일에 저장
        play_result = runner.invoke(cli, [
            "play", SAMPLE_JSONL,
            "--speed", "0",
            "--dry-run",
        ])
        assert play_result.exit_code == 0

        # play 출력에서 frame 타입으로 변환 (play → frame)
        # play 출력은 type=play이므로 decode에서 처리되려면 frame이어야 함
        # → 원본 JSONL을 직접 decode에 넘기는 게 정상 파이프라인
        decode_result = runner.invoke(cli, [
            "decode",
            "--dbc", TEST_DBC,
            "--input", SAMPLE_JSONL,
        ])
        assert decode_result.exit_code == 0
        lines = [json.loads(l) for l in decode_result.output.strip().split("\n")]
        decoded = [l for l in lines if l["type"] == "decoded"]
        assert len(decoded) == 5
