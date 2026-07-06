from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calculations.domain.constants import GROUP_BY_CHOICES, GROUP_BY_INNER_CHOICES


@dataclass(frozen=True)
class ScenarioAbsoluteRequestDTO:
    cache_key: str
    group_by: str = "cargo_group"
    group_by_inner: str = "none"
    include_fallout: bool = False

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.cache_key or not isinstance(self.cache_key, str):
            errors.append("Некорректный cache_key")
        if self.group_by not in GROUP_BY_CHOICES:
            errors.append("Некорректный group_by")
        if self.group_by_inner not in GROUP_BY_INNER_CHOICES:
            errors.append("Некорректный group_by_inner")
        if self.group_by_inner != "none" and self.group_by_inner == self.group_by:
            errors.append("group_by_inner не может совпадать с group_by")
        return errors


@dataclass(frozen=True)
class AbsoluteTableRowDTO:
    label: str
    is_subtotal: bool
    years: dict[str, str]
    total: str
    years_fallout: dict[str, str] | None = None
    total_fallout: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "label": self.label,
            "is_subtotal": self.is_subtotal,
            "years": self.years,
            "total": self.total,
        }
        if self.years_fallout is not None:
            payload["years_fallout"] = self.years_fallout
        if self.total_fallout is not None:
            payload["total_fallout"] = self.total_fallout
        return payload


@dataclass(frozen=True)
class ScenarioAbsoluteResponseDTO:
    years: list[int]
    total_column_label: str
    unit: str
    rows: list[AbsoluteTableRowDTO]
    show_fallout_adjusted: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "years": self.years,
            "total_column_label": self.total_column_label,
            "unit": self.unit,
            "show_fallout_adjusted": self.show_fallout_adjusted,
            "table": {"rows": [row.to_api_dict() for row in self.rows]},
        }
