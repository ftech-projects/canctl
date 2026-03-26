"""Internal Message schema — 모든 cmd/core에서 통일 사용하는 CAN 프레임 데이터 클래스"""

from __future__ import annotations

import time
from dataclasses import dataclass, field


def _now_ns() -> int:
    """현재 시각 나노초 반환."""
    return time.time_ns()


@dataclass(slots=True)
class CanFrame:
    """canctl 내부 통일 CAN 프레임 표현.

    모든 cmd에서 이 클래스를 통해 프레임을 생성/전달.
    timestamp는 int 나노초 기준, 출력 시 float 초로 변환.
    """
    arb_id: int
    data: bytes
    is_extended: bool = False
    is_fd: bool = False
    dlc: int = 0
    channel: str = ""
    ts_ns: int = field(default_factory=_now_ns)

    def __post_init__(self):
        if self.dlc == 0:
            self.dlc = len(self.data)

    @property
    def ts(self) -> float:
        """나노초 → float 초 변환 (JSONL 출력용)."""
        return self.ts_ns / 1_000_000_000

    @property
    def id_hex(self) -> str:
        """'0x201' 형식 ID 문자열."""
        return f"0x{self.arb_id:X}"

    @property
    def data_hex(self) -> str:
        """대문자 hex 문자열."""
        return self.data.hex().upper()

    def to_record(self, record_type: str = "frame",
                  bus: str | None = None) -> dict:
        """JSONL 출력용 dict 변환."""
        record = {
            "type": record_type,
            "ts": self.ts,
            "bus": bus or self.channel,
            "id": self.id_hex,
            "ext": self.is_extended,
            "dlc": self.dlc,
            "data": self.data_hex,
        }
        if self.is_fd:
            record["fd"] = True
        return record

    @classmethod
    def from_can_message(cls, msg, channel: str = "") -> CanFrame:
        """python-can Message → CanFrame 변환."""
        return cls(
            arb_id=msg.arbitration_id,
            data=bytes(msg.data),
            is_extended=msg.is_extended_id,
            is_fd=getattr(msg, "is_fd", False),
            dlc=msg.dlc,
            channel=channel,
        )

    @classmethod
    def from_record(cls, record: dict) -> CanFrame:
        """JSONL dict → CanFrame 변환."""
        arb_id = int(record.get("id", "0x0"), 16)
        data = bytes.fromhex(record.get("data", ""))
        ts_float = record.get("ts", 0.0)
        ts_ns = int(ts_float * 1_000_000_000) if ts_float else _now_ns()
        return cls(
            arb_id=arb_id,
            data=data,
            is_extended=record.get("ext", False),
            is_fd=record.get("fd", False),
            dlc=record.get("dlc", len(data)),
            channel=record.get("bus", ""),
            ts_ns=ts_ns,
        )
