"""canctl remote — FtechEngine diag/exec API를 통한 원격 canctl 실행"""

import json
import subprocess
import sys
from pathlib import Path


def load_targets(path: str | None = None) -> list[dict]:
    """deploy-targets.json에서 대상 PC 목록 로드."""
    search_paths = [
        path,
        "deploy-targets.json",
        str(Path.home() / "Desktop" / "FtechEngine" / "deploy-targets.json"),
    ]
    for p in search_paths:
        if p and Path(p).exists():
            with open(p, encoding="utf-8") as f:
                return json.load(f)
    return []


def find_target(targets: list[dict], name: str) -> dict | None:
    """이름 또는 IP로 대상 PC 찾기."""
    for t in targets:
        if t["name"] == name or t["ip"] == name:
            return t
    return None


def exec_remote(ip: str, port: int, command: str, timeout: int = 30) -> dict:
    """FtechEngine diag/exec API로 원격 명령 실행.

    Returns:
        {"ok": bool, "stdout": str, "stderr": str, "exit_code": int}
    """
    url = f"http://{ip}:{port}/api/v1/diag/exec"
    payload = json.dumps({"command": command})

    try:
        result = subprocess.run(
            [
                "curl", "-s", "-X", "POST", url,
                "-H", "Content-Type: application/json",
                "-d", payload,
                "--connect-timeout", "5",
                "--max-time", str(timeout),
            ],
            capture_output=True, text=True, timeout=timeout + 10,
        )
        if result.returncode != 0:
            return {"ok": False, "stdout": "", "stderr": result.stderr,
                    "exit_code": result.returncode}

        try:
            resp = json.loads(result.stdout)
            return {
                "ok": True,
                "stdout": resp.get("output", resp.get("stdout", result.stdout)),
                "stderr": resp.get("error", resp.get("stderr", "")),
                "exit_code": resp.get("exitCode", 0),
            }
        except json.JSONDecodeError:
            return {"ok": True, "stdout": result.stdout, "stderr": "",
                    "exit_code": 0}
    except subprocess.TimeoutExpired:
        return {"ok": False, "stdout": "", "stderr": "timeout",
                "exit_code": 2}
    except Exception as e:
        return {"ok": False, "stdout": "", "stderr": str(e),
                "exit_code": 1}


def exec_canctl(ip: str, port: int, canctl_args: str,
                timeout: int = 30) -> list[dict]:
    """원격 canctl 실행 후 JSONL 파싱.

    Returns:
        파싱된 JSONL 레코드 리스트
    """
    result = exec_remote(ip, port, f"canctl {canctl_args}", timeout)

    if not result["ok"]:
        return [{"type": "error", "code": "REMOTE_FAIL",
                 "message": result["stderr"]}]

    records = []
    for line in result["stdout"].strip().split("\n"):
        line = line.strip()
        if not line:
            continue
        try:
            records.append(json.loads(line))
        except json.JSONDecodeError:
            continue

    return records


def upload_file(ip: str, port: int, local_path: str,
                remote_dir: str = "C:/canctl-data") -> bool:
    """원격 PC에 파일 업로드 (mkdir + base64 전송)."""
    path = Path(local_path)
    if not path.exists():
        return False

    # 원격 디렉토리 생성
    exec_remote(ip, port, f'mkdir "{remote_dir}" 2>nul')

    # 파일 내용을 base64로 인코딩하여 전송
    import base64
    content = path.read_bytes()
    b64 = base64.b64encode(content).decode()

    remote_path = f"{remote_dir}/{path.name}"
    # PowerShell로 base64 디코딩하여 파일 생성
    ps_cmd = (
        f'powershell "[IO.File]::WriteAllBytes(\'{remote_path}\', '
        f'[Convert]::FromBase64String(\'{b64}\'))"'
    )
    result = exec_remote(ip, port, ps_cmd, timeout=60)
    return result["ok"]


if __name__ == "__main__":
    # 간단 테스트: python -m canctl.remote <target> <canctl_args>
    if len(sys.argv) < 3:
        print("Usage: python -m canctl.remote <target_name_or_ip> <canctl args...>")
        sys.exit(1)

    targets = load_targets()
    target_name = sys.argv[1]
    canctl_args = " ".join(sys.argv[2:])

    target = find_target(targets, target_name)
    if target:
        ip, port = target["ip"], target["port"]
    else:
        ip, port = target_name, 5050

    records = exec_canctl(ip, port, canctl_args)
    for r in records:
        print(json.dumps(r, ensure_ascii=False))
