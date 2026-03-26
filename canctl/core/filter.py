"""CAN 필터 통합 모듈 — HW 필터 + SW fallback"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(slots=True)
class CanFilter:
    """단일 CAN 필터 규칙."""
    can_id: int
    can_mask: int = 0x1FFFFFFF
    extended: bool = False

    @classmethod
    def from_id(cls, id_hex: str,
                mask: int = 0x1FFFFFFF) -> CanFilter:
        """'0x201' 문자열에서 필터 생성."""
        can_id = int(id_hex, 16)
        return cls(
            can_id=can_id,
            can_mask=mask,
            extended=(can_id > 0x7FF),
        )


class FilterManager:
    """HW 필터 설정 + SW fallback 통합 관리.

    사용법:
        fm = FilterManager(["0x201", "0x202"], mask=0x7FF)
        fm.apply_hw_filter(bus)  # HW 필터 시도
        if fm.match(msg):        # SW fallback 체크
            ...
    """

    def __init__(self, filter_ids: list[str],
                 mask: int = 0x1FFFFFFF):
        self._filters: list[CanFilter] = []
        self._id_set: set[int] = set()
        self._mask = mask

        for id_hex in filter_ids:
            filt = CanFilter.from_id(id_hex, mask)
            self._filters.append(filt)
            self._id_set.add(filt.can_id)

    @property
    def id_set(self) -> set[int]:
        """필터 ID int set (SW 필터용)."""
        return self._id_set

    @property
    def is_empty(self) -> bool:
        return len(self._filters) == 0

    def apply_hw_filter(self, bus) -> bool:
        """버스에 HW 필터 설정 시도. 실패 시 False."""
        if self.is_empty:
            return True
        try:
            hw_filters = [
                {
                    "can_id": f.can_id,
                    "can_mask": f.can_mask,
                    "extended": f.extended,
                }
                for f in self._filters
            ]
            bus.set_filters(hw_filters)
            return True
        except Exception:
            return False

    def match(self, arb_id: int) -> bool:
        """SW 필터 체크. 필터 비어있으면 항상 True (pass-all)."""
        if self.is_empty:
            return True
        return arb_id in self._id_set

    def to_dict_list(self) -> list[dict]:
        """디버깅/출력용 dict 목록."""
        return [
            {
                "id": f"0x{f.can_id:X}",
                "mask": f"0x{f.can_mask:X}",
                "ext": f.extended,
            }
            for f in self._filters
        ]
