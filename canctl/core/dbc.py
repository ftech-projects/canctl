"""cantools DBC 래핑 — 복수 DBC 로드 및 디코딩"""

from typing import Sequence

import cantools

from .errors import CanctlError, DBC_PARSE_FAIL


class DbcDecoder:
    """복수 DBC 파일을 로드하고 CAN 프레임을 디코딩."""

    def __init__(self, dbc_paths: Sequence[str]):
        self._db = cantools.database.Database()
        for path in dbc_paths:
            try:
                self._db.add_dbc_file(path)
            except Exception as e:
                raise CanctlError(DBC_PARSE_FAIL, f"{path}: {e}")

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
        except Exception:
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
