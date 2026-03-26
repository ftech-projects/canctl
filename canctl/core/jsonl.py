"""JSONL 파일 읽기/쓰기 유틸"""

import json
import sys
from pathlib import Path
from typing import IO, Generator

from .errors import CanctlError, FILE_NOT_FOUND


def read_jsonl(source: str | None = None) -> Generator[dict, None, None]:
    """JSONL 소스에서 레코드를 하나씩 yield.

    source=None이면 stdin에서 읽음.
    """
    if source is None:
        yield from _read_stream(sys.stdin)
    else:
        path = Path(source)
        if not path.exists():
            raise CanctlError(FILE_NOT_FOUND, f"file not found: {source}")
        with open(path, "r", encoding="utf-8") as f:
            yield from _read_stream(f)


def _read_stream(stream: IO) -> Generator[dict, None, None]:
    for line in stream:
        line = line.strip()
        if not line:
            continue
        try:
            yield json.loads(line)
        except json.JSONDecodeError:
            continue  # 파싱 불가 라인 무시


def open_jsonl_writer(path: str | None):
    """JSONL 출력 파일 열기. None이면 stdout 반환."""
    if path is None:
        return sys.stdout
    return open(path, "w", encoding="utf-8")
