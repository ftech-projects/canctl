"""원격 실행 시뮬레이션 테스트 — subprocess로 canctl CLI 호출, FtechEngine diag/exec 시나리오 재현

FtechEngine diag/exec는 cmd /c로 명령 실행 후 stdout/stderr를 전체 버퍼링하여 반환한다.
이 테스트는 subprocess.run()으로 동일한 패턴을 시뮬레이션한다:
  1. canctl CLI를 subprocess로 호출
  2. stdout 전체 캡처 → 줄 단위 JSON 파싱
  3. exit code 검증
  4. JSONL 스키마 검증
"""

import json
import os
import subprocess
import sys

import pytest

# 테스트 데이터 경로
TEST_DIR = os.path.dirname(__file__)
SAMPLE_JSONL = os.path.join(TEST_DIR, "sample_capture.jsonl")
TEST_DBC = os.path.join(TEST_DIR, "test.dbc")


def run_canctl(*args: str, timeout: float = 10.0) -> subprocess.CompletedProcess:
    """canctl CLI를 subprocess로 실행 — diag/exec 시뮬레이션

    FtechEngine diag/exec와 동일하게:
    - stdout 전체 버퍼링 (capture_output=True)
    - UTF-8 디코딩
    - timeout 적용
    """
    cmd = [sys.executable, "-m", "canctl"] if not _canctl_path() else [_canctl_path()]
    cmd.extend(args)
    return subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
    )


def _canctl_path() -> str | None:
    """canctl 실행 파일 경로 탐색"""
    import shutil
    return shutil.which("canctl")


def parse_jsonl(stdout: str) -> list[dict]:
    """stdout에서 JSONL 파싱 — 빈 줄 무시"""
    lines = []
    for line in stdout.strip().split("\n"):
        line = line.strip()
        if line:
            lines.append(json.loads(line))
    return lines


def find_by_type(records: list[dict], type_name: str) -> list[dict]:
    """특정 type의 레코드만 필터"""
    return [r for r in records if r.get("type") == type_name]


# ---------------------------------------------------------------------------
# diag/exec 응답 시뮬레이션 헬퍼
# ---------------------------------------------------------------------------

def simulate_exec_response(proc: subprocess.CompletedProcess) -> dict:
    """subprocess 결과를 FtechEngine ExecResponse 형식으로 변환

    실제 ExecResponse 스키마:
    { "Command": str, "ExitCode": int, "Stdout": str, "Stderr": str }
    """
    return {
        "Command": " ".join(proc.args) if isinstance(proc.args, list) else proc.args,
        "ExitCode": proc.returncode,
        "Stdout": proc.stdout or "",
        "Stderr": proc.stderr or "",
    }


# ===========================================================================
# send 원격 실행 테스트
# ===========================================================================

class TestRemoteSend:
    """send --dry-run 원격 실행 시뮬레이션"""

    def test_send_single_frame(self):
        """단일 프레임 송신 → exit code 0, JSONL 파싱"""
        proc = run_canctl("send", "--id", "0x201", "--data", "0102030405060708", "--dry-run")
        assert proc.returncode == 0

        # diag/exec 응답 시뮬레이션
        resp = simulate_exec_response(proc)
        assert resp["ExitCode"] == 0
        assert resp["Stderr"] == ""

        # Stdout에서 JSONL 파싱
        records = parse_jsonl(resp["Stdout"])
        sends = find_by_type(records, "send")
        assert len(sends) == 1
        assert sends[0]["id"] == "0x201"
        assert sends[0]["status"] == "ok"
        assert sends[0]["data"] == "0102030405060708"

        # summary 존재 확인
        summary = find_by_type(records, "summary")
        assert len(summary) == 1
        assert summary[0]["sent"] == 1

    def test_send_repeat(self):
        """반복 송신 → summary.sent == repeat 횟수"""
        proc = run_canctl(
            "send", "--id", "0x18FF50E5", "--ext",
            "--data", "AABB", "--repeat", "5", "--dry-run",
        )
        assert proc.returncode == 0
        records = parse_jsonl(proc.stdout)
        sends = find_by_type(records, "send")
        assert len(sends) == 5
        assert all(s["ext"] is True for s in sends)

        summary = find_by_type(records, "summary")
        assert summary[0]["sent"] == 5

    def test_send_fd_mode(self):
        """CAN FD 프레임 송신 확인"""
        proc = run_canctl(
            "send", "--id", "0x201",
            "--data", "0102030405060708090A0B0C",
            "--fd", "--dry-run",
        )
        assert proc.returncode == 0
        records = parse_jsonl(proc.stdout)
        sends = find_by_type(records, "send")
        assert len(sends) == 1
        assert sends[0].get("fd") is True


# ===========================================================================
# recv 원격 실행 테스트
# ===========================================================================

class TestRemoteRecv:
    """recv --dry-run 원격 실행 시뮬레이션 — timeout 필수 (스트리밍 불가)"""

    def test_recv_timeout(self):
        """타임아웃 발생 → error + summary, exit code 0"""
        proc = run_canctl(
            "recv", "--id", "0x201", "--timeout", "0.3", "--dry-run",
        )
        # recv timeout은 에러가 아니라 정상 종료
        assert proc.returncode == 0

        records = parse_jsonl(proc.stdout)
        errors = find_by_type(records, "error")
        assert any(e["code"] == "TIMEOUT" for e in errors)

        summary = find_by_type(records, "summary")
        assert summary[0]["received"] == 0
        assert summary[0]["timeout"] is True

    def test_recv_with_requires(self):
        """--requires 포함 수신 → periodic_start/stop 이벤트"""
        proc = run_canctl(
            "recv", "--id", "0x201", "--timeout", "0.3",
            "--requires", "0x700:00:100ms", "--dry-run",
        )
        assert proc.returncode == 0

        records = parse_jsonl(proc.stdout)
        starts = find_by_type(records, "periodic_start")
        stops = find_by_type(records, "periodic_stop")
        assert len(starts) == 1
        assert starts[0]["id"] == "0x700"
        assert starts[0]["interval_ms"] == 100
        assert len(stops) == 1

    def test_recv_exec_response_schema(self):
        """ExecResponse 스키마 검증 — Stdout/Stderr/ExitCode 필드"""
        proc = run_canctl(
            "recv", "--id", "0x201", "--timeout", "0.3", "--dry-run",
        )
        resp = simulate_exec_response(proc)
        assert "Command" in resp
        assert "ExitCode" in resp
        assert "Stdout" in resp
        assert "Stderr" in resp
        assert isinstance(resp["ExitCode"], int)
        assert isinstance(resp["Stdout"], str)


# ===========================================================================
# play 원격 실행 테스트
# ===========================================================================

class TestRemotePlay:
    """play --dry-run 원격 실행 시뮬레이션"""

    def test_play_replay(self):
        """캡처 파일 재생 → play 레코드 + summary"""
        proc = run_canctl(
            "play", SAMPLE_JSONL, "--speed", "0", "--dry-run",
        )
        assert proc.returncode == 0

        records = parse_jsonl(proc.stdout)
        plays = find_by_type(records, "play")
        assert len(plays) == 5
        assert all(p["status"] == "sent" for p in plays)

        summary = find_by_type(records, "summary")
        assert summary[0]["played"] == 5

    def test_play_burst(self):
        """burst 재생 → 프레임 수 = 원본 × burst"""
        proc = run_canctl(
            "play", SAMPLE_JSONL, "--speed", "0",
            "--burst", "3", "--dry-run",
        )
        assert proc.returncode == 0

        records = parse_jsonl(proc.stdout)
        plays = find_by_type(records, "play")
        assert len(plays) == 15  # 5 × 3

        summary = find_by_type(records, "summary")
        assert summary[0]["played"] == 15


# ===========================================================================
# monitor 원격 실행 테스트
# ===========================================================================

class TestRemoteMonitor:
    """monitor --dry-run 원격 실행 시뮬레이션 — duration 필수 (스트리밍 불가)"""

    def test_monitor_duration(self):
        """짧은 duration → summary 반환"""
        proc = run_canctl(
            "monitor", "--duration", "0.3", "--dry-run",
        )
        assert proc.returncode == 0

        records = parse_jsonl(proc.stdout)
        summary = find_by_type(records, "summary")
        assert len(summary) == 1
        assert "total" in summary[0]
        assert "elapsed" in summary[0]

    def test_monitor_exec_buffering(self):
        """stdout 전체 버퍼링 시뮬레이션 — 모든 출력이 한번에 캡처됨"""
        proc = run_canctl(
            "monitor", "--duration", "0.3", "--dry-run",
        )
        resp = simulate_exec_response(proc)

        # 전체 Stdout를 한번에 파싱 가능해야 함
        records = parse_jsonl(resp["Stdout"])
        assert len(records) >= 1  # 최소 summary
        # 모든 줄이 유효한 JSON
        for r in records:
            assert "type" in r
            assert "ts" in r


# ===========================================================================
# --pretty 모드 테스트
# ===========================================================================

class TestRemotePretty:
    """--pretty 모드 — 사람용 출력, JSONL이 아님"""

    def test_pretty_not_jsonl(self):
        """--pretty 출력은 JSON 파싱 불가"""
        proc = run_canctl(
            "--pretty", "send", "--id", "0x201", "--data", "0102", "--dry-run",
        )
        assert proc.returncode == 0
        # pretty 모드는 JSONL이 아니므로 파싱하면 실패해야 함
        for line in proc.stdout.strip().split("\n"):
            line = line.strip()
            if not line:
                continue
            with pytest.raises(json.JSONDecodeError):
                json.loads(line)


# ===========================================================================
# exit code 검증
# ===========================================================================

class TestRemoteExitCode:
    """exit code 검증 — diag/exec ExitCode 필드 매핑"""

    def test_success_exit_0(self):
        """정상 실행 → exit code 0"""
        proc = run_canctl("send", "--id", "0x201", "--data", "FF", "--dry-run")
        assert proc.returncode == 0

    def test_invalid_arg_exit_1(self):
        """잘못된 인자 → exit code != 0"""
        proc = run_canctl("send", "--id", "INVALID_ID", "--data", "FF", "--dry-run")
        assert proc.returncode != 0

    def test_missing_required_exit_nonzero(self):
        """필수 인자 누락 → exit code != 0"""
        proc = run_canctl("send", "--dry-run")
        assert proc.returncode != 0


# ===========================================================================
# JSONL 스키마 공통 필드 검증
# ===========================================================================

class TestJsonlSchema:
    """모든 JSONL 레코드의 공통 필드 검증"""

    def test_all_records_have_type_and_ts(self):
        """모든 레코드에 type, ts 필드 존재"""
        proc = run_canctl("send", "--id", "0x201", "--data", "FF", "--dry-run")
        records = parse_jsonl(proc.stdout)
        for r in records:
            assert "type" in r, f"type 필드 누락: {r}"
            assert "ts" in r, f"ts 필드 누락: {r}"

    def test_ts_is_float(self):
        """ts 필드는 float (unix timestamp)"""
        proc = run_canctl(
            "play", SAMPLE_JSONL, "--speed", "0", "--dry-run",
        )
        records = parse_jsonl(proc.stdout)
        for r in records:
            assert isinstance(r["ts"], (int, float)), f"ts가 숫자가 아님: {r['ts']}"

    def test_bus_field_format(self):
        """bus 필드는 'interface:channel' 형식"""
        proc = run_canctl("send", "--id", "0x201", "--data", "FF", "--dry-run")
        records = parse_jsonl(proc.stdout)
        for r in records:
            if r.get("bus"):
                assert ":" in r["bus"], f"bus 형식 오류: {r['bus']}"


# ===========================================================================
# diag/exec 시나리오 통합 테스트
# ===========================================================================

class TestDiagExecScenario:
    """FtechEngine diag/exec 원격 실행 전체 시나리오 시뮬레이션"""

    def test_full_send_scenario(self):
        """원격지에서 CAN 프레임 송신 시나리오

        1. diag/exec로 canctl send 실행
        2. ExecResponse.Stdout에서 JSONL 파싱
        3. 결과 검증
        """
        # Step 1: diag/exec 실행 시뮬레이션
        proc = run_canctl(
            "send", "--id", "0x201", "--data", "FF3C000000000000",
            "--repeat", "3", "--dry-run",
        )

        # Step 2: ExecResponse 변환
        resp = simulate_exec_response(proc)
        assert resp["ExitCode"] == 0

        # Step 3: Stdout에서 JSONL 줄별 파싱
        records = parse_jsonl(resp["Stdout"])
        sends = find_by_type(records, "send")
        summary = find_by_type(records, "summary")

        assert len(sends) == 3
        assert summary[0]["sent"] == 3

    def test_full_recv_with_timeout_scenario(self):
        """원격지에서 CAN 수신 대기 시나리오

        diag/exec 제약: 스트리밍 불가 → --timeout 필수
        """
        proc = run_canctl(
            "recv", "--id", "0x201", "--timeout", "0.5", "--dry-run",
        )
        resp = simulate_exec_response(proc)
        assert resp["ExitCode"] == 0

        records = parse_jsonl(resp["Stdout"])
        summary = find_by_type(records, "summary")
        assert summary[0]["timeout"] is True

    def test_full_monitor_capture_scenario(self):
        """원격지에서 버스 모니터링 시나리오

        diag/exec 제약: 스트리밍 불가 → --duration 필수
        """
        proc = run_canctl(
            "monitor", "--duration", "0.3", "--dry-run",
        )
        resp = simulate_exec_response(proc)
        assert resp["ExitCode"] == 0

        records = parse_jsonl(resp["Stdout"])
        summary = find_by_type(records, "summary")
        assert len(summary) == 1

    def test_full_play_decode_pipeline(self):
        """원격지에서 재생→디코드 파이프라인 시나리오

        diag/exec는 파이프 불가 → 별도 호출로 시뮬레이션
        """
        # Step 1: play로 캡처 재생
        play_proc = run_canctl(
            "play", SAMPLE_JSONL, "--speed", "0", "--dry-run",
        )
        assert play_proc.returncode == 0

        # Step 2: 별도 호출로 decode (파이프 대신 파일 입력)
        decode_proc = run_canctl(
            "decode", "--dbc", TEST_DBC, "--input", SAMPLE_JSONL,
        )
        assert decode_proc.returncode == 0

        records = parse_jsonl(decode_proc.stdout)
        decoded = find_by_type(records, "decoded")
        assert len(decoded) == 5
