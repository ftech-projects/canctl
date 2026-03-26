"""cantools DBC 래핑 — 복수 DBC 로드, conflict 감지, 디코딩"""

from __future__ import annotations

from typing import Sequence

import cantools

from .errors import (
    CanctlError, DBC_PARSE_FAIL, DECODE_ERROR,
    INVALID_DBC, SIGNAL_CONFLICT,
)
from .output import emit_warning


# DBC 충돌 해결 정책
CONFLICT_ERROR = "error"       # 중복 시 에러 발생
CONFLICT_LATER_WINS = "later"  # 나중에 로드된 DBC 우선
CONFLICT_FIRST_WINS = "first"  # 먼저 로드된 DBC 유지


class DbcDecoder:
    """복수 DBC 파일을 로드하고 CAN 프레임을 디코딩.

    conflict_policy:
        "error"  — frame_id 중복 시 SIGNAL_CONFLICT 에러 발생
        "later"  — 나중에 로드된 DBC가 우선 (기본)
        "first"  — 먼저 로드된 DBC 유지, 이후 중복 무시
    """

    def __init__(self, dbc_paths: Sequence[str],
                 conflict_policy: str = CONFLICT_LATER_WINS):
        self._db = cantools.database.Database()
        self._conflicts: list[dict] = []  # 충돌 기록
        self._loaded_ids: dict[int, str] = {}  # frame_id → 소스 DBC 경로
        self._policy = conflict_policy

        for path in dbc_paths:
            self._load_dbc(path)

    def _load_dbc(self, path: str) -> None:
        """단일 DBC 파일 로드 + conflict 처리."""
        try:
            tmp_db = cantools.database.load_file(path)
        except Exception as e:
            raise CanctlError(DBC_PARSE_FAIL, f"{path}: {e}")

        for msg in tmp_db.messages:
            fid = msg.frame_id
            if fid in self._loaded_ids:
                conflict_info = {
                    "frame_id": f"0x{fid:X}",
                    "existing_source": self._loaded_ids[fid],
                    "new_source": path,
                    "msg_name": msg.name,
                }
                self._conflicts.append(conflict_info)

                if self._policy == CONFLICT_ERROR:
                    raise CanctlError(
                        SIGNAL_CONFLICT,
                        f"frame_id 0x{fid:X} conflict: "
                        f"{self._loaded_ids[fid]} vs {path}",
                    )
                elif self._policy == CONFLICT_FIRST_WINS:
                    # 기존 유지, 경고만 출력
                    emit_warning(
                        SIGNAL_CONFLICT,
                        f"frame_id 0x{fid:X} duplicate in {path}, "
                        f"keeping {self._loaded_ids[fid]}",
                    )
                    continue
                else:  # CONFLICT_LATER_WINS (기본)
                    # 기존 메시지 제거 후 새로 추가
                    try:
                        existing = self._db.get_message_by_frame_id(fid)
                        self._db._messages.remove(existing)
                    except (KeyError, ValueError):
                        pass
                    emit_warning(
                        SIGNAL_CONFLICT,
                        f"frame_id 0x{fid:X} overridden by {path}",
                    )

            self._loaded_ids[fid] = path

        # conflict 처리 후 전체 메시지 추가
        try:
            self._db.add_dbc_file(path)
        except Exception as e:
            raise CanctlError(DBC_PARSE_FAIL, f"{path}: {e}")

    @property
    def conflicts(self) -> list[dict]:
        """감지된 충돌 목록."""
        return list(self._conflicts)

    def decode(self, arb_id: int, data: bytes) -> dict | None:
        """메시지 디코딩. 매칭 실패 시 None 반환.

        Returns:
            {"msg": "메시지명", "signals": {이름: {"value", "unit", "min", "max"}}}
        """
        try:
            msg = self._db.get_message_by_frame_id(arb_id)
        except KeyError:
            return None

        try:
            decoded = msg.decode(data)
        except Exception as e:
            emit_warning(
                DECODE_ERROR,
                f"decode failed for 0x{arb_id:X}: {e}",
            )
            return None

        signals = {}
        for sig in msg.signals:
            if sig.name in decoded:
                signals[sig.name] = {
                    "value": decoded[sig.name],
                    "unit": sig.unit or "",
                    "min": sig.minimum,
                    "max": sig.maximum,
                }
        return {"msg": msg.name, "signals": signals}

    def try_decode_simple(self, arb_id: int, data: bytes) -> dict | None:
        """간단 디코딩 — signals를 {이름: 값} 형태로만 반환."""
        try:
            msg = self._db.get_message_by_frame_id(arb_id)
            decoded = msg.decode(data)
            return {k: v for k, v in decoded.items()}
        except Exception:
            return None
