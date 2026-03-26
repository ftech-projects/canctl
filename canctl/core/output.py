"""JSONL stdout 출력 헬퍼 — 공통 베이스(type, ts, bus) 보장"""

import json
import sys
import time
from datetime import datetime

# 전역 pretty 모드 플래그
_pretty = False


def set_pretty(enabled: bool) -> None:
    global _pretty
    _pretty = enabled


def is_pretty() -> bool:
    return _pretty


def _now() -> float:
    return time.time()


def _ts_str(ts: float) -> str:
    """타임스탬프를 사람이 읽기 좋은 형태로 변환."""
    return datetime.fromtimestamp(ts).strftime("%H:%M:%S.%f")[:-3]


# ANSI 컬러
_COLORS = {
    "frame":    "\033[36m",   # cyan
    "decoded":  "\033[32m",   # green
    "send":     "\033[33m",   # yellow
    "play":     "\033[33m",   # yellow
    "error":    "\033[31m",   # red
    "warning":  "\033[35m",   # magenta
    "summary":  "\033[97m",   # white bold
    "stats":    "\033[90m",   # gray
    "hw":       "\033[34m",   # blue
    "periodic_start": "\033[90m",
    "periodic_stop":  "\033[90m",
    "unknown":  "\033[90m",   # gray
}
_RESET = "\033[0m"


def _pretty_format(record: dict) -> str:
    """사람용 한 줄 포맷."""
    rtype = record.get("type", "?")
    ts = _ts_str(record["ts"]) if "ts" in record else "??:??:??"
    color = _COLORS.get(rtype, "")

    if rtype == "frame":
        sid = record.get("id", "?")
        data = record.get("data", "")
        signals = record.get("signals", {})
        # data를 2자리씩 공백 구분
        data_fmt = " ".join(data[i:i+2] for i in range(0, len(data), 2))
        line = f"{ts}  {sid:<12s} [{record.get('dlc', '?')}]  {data_fmt}"
        if signals:
            sig_str = "  ".join(f"{k}={v}" for k, v in signals.items())
            line += f"  | {sig_str}"
        return f"{color}{line}{_RESET}"

    elif rtype == "decoded":
        sid = record.get("id", "?")
        msg = record.get("msg", "?")
        signals = record.get("signals", {})
        parts = []
        for name, info in signals.items():
            if isinstance(info, dict):
                val = info.get("value", "?")
                unit = info.get("unit", "")
                parts.append(f"{name}={val}{unit}")
            else:
                parts.append(f"{name}={info}")
        sig_str = "  ".join(parts)
        return f"{color}{ts}  {sid:<12s} {msg:<20s} {sig_str}{_RESET}"

    elif rtype == "send":
        sid = record.get("id", "?")
        data = record.get("data", "")
        data_fmt = " ".join(data[i:i+2] for i in range(0, len(data), 2))
        status = record.get("status", "?")
        return f"{color}{ts}  TX  {sid:<12s} [{record.get('dlc', '?')}]  {data_fmt}  {status}{_RESET}"

    elif rtype == "play":
        sid = record.get("id", "?")
        data = record.get("data", "")
        data_fmt = " ".join(data[i:i+2] for i in range(0, len(data), 2))
        return f"{color}{ts}  PLAY {sid:<12s} {data_fmt}{_RESET}"

    elif rtype == "error":
        code = record.get("code", "?")
        msg = record.get("message", "?")
        return f"{color}ERROR [{code}] {msg}{_RESET}"

    elif rtype == "warning":
        code = record.get("code", "?")
        msg = record.get("message", "?")
        return f"{color}WARN  [{code}] {msg}{_RESET}"

    elif rtype == "summary":
        parts = []
        for k, v in record.items():
            if k not in ("type", "ts", "bus"):
                parts.append(f"{k}={v}")
        return f"{color}--- Summary: {', '.join(parts)} ---{_RESET}"

    elif rtype == "stats":
        total = record.get("total", 0)
        dropped = record.get("dropped", 0)
        elapsed = record.get("elapsed", 0)
        return f"{color}[stats] {total} frames, {dropped} dropped, {elapsed}s{_RESET}"

    elif rtype == "hw":
        iface = record.get("interface", "?")
        ch = record.get("channel", "?")
        state = record.get("state", "?")
        return f"{color}{iface:<8s} {ch:<20s} {state}{_RESET}"

    elif rtype in ("periodic_start", "periodic_stop"):
        sid = record.get("id", "?")
        action = "START" if "start" in rtype else "STOP"
        interval = record.get("interval_ms", "")
        extra = f" every {interval}ms" if interval else ""
        return f"{color}PERIODIC {action} {sid}{extra}{_RESET}"

    else:
        return f"{color}{ts}  [{rtype}] {json.dumps(record, ensure_ascii=False)}{_RESET}"


def emit(record: dict, *, file=None) -> None:
    """record에 ts 없으면 현재 시각 추가 후 출력.

    pretty 모드면 사람용, 아니면 JSONL.
    """
    if "ts" not in record:
        record["ts"] = _now()
    if "bus" not in record:
        record["bus"] = None

    out = file or sys.stdout

    if _pretty and (file is None or file is sys.stdout):
        out.write(_pretty_format(record) + "\n")
    else:
        line = json.dumps(record, ensure_ascii=False, separators=(",", ":"))
        out.write(line + "\n")
    out.flush()


def emit_error(code: str, message: str, *, bus: str | None = None) -> None:
    """에러 출력."""
    emit({"type": "error", "bus": bus, "code": code, "message": message})


def emit_warning(code: str, message: str, *, bus: str | None = None, **extra) -> None:
    """경고 출력."""
    record = {"type": "warning", "bus": bus, "code": code, "message": message}
    record.update(extra)
    emit(record)


def format_bus(interface: str, channel: str) -> str:
    """bus 필드 문자열 생성. 예: 'pcan:PCAN_USBBUS1'"""
    return f"{interface}:{channel}"
