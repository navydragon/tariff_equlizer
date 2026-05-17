from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calculations.domain.constants import (
    CUBE_GROUP_BY_CHOICES,
    CUBE_GROUP_BY_INNER_CHOICES,
)


@dataclass(frozen=True)
class ScenarioEffectsCubeRequestDTO:
    cache_key: str
    group_by: str = "cargo_group"
    group_by_inner: str = "none"
    cargo_groups: list[str] = field(default_factory=list)
    holdings: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.cache_key or not isinstance(self.cache_key, str):
            errors.append("Некорректный cache_key")
        if self.group_by not in CUBE_GROUP_BY_CHOICES:
            errors.append("Некорректный group_by")
        if self.group_by_inner not in CUBE_GROUP_BY_INNER_CHOICES:
            errors.append("Некорректный group_by_inner")
        if self.group_by == "tariff_decision" and self.group_by_inner != "none":
            errors.append(
                "group_by_inner недоступен при группировке «Тарифные решения»",
            )
        if (
            self.group_by_inner != "none"
            and self.group_by_inner == self.group_by
            and self.group_by != "tariff_decision"
        ):
            errors.append("group_by_inner не может совпадать с group_by")
        if not isinstance(self.cargo_groups, list):
            errors.append("cargo_groups должен быть списком")
        if not isinstance(self.holdings, list):
            errors.append("holdings должен быть списком")
        return errors


@dataclass(frozen=True)
class CubeTableRowDTO:
    group_label: str
    group_inner_label: str | None
    effect_label: str
    years: dict[int, str]
    total: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "group_label": self.group_label,
            "group_inner_label": self.group_inner_label,
            "effect_label": self.effect_label,
            "years": {str(year): value for year, value in self.years.items()},
            "total": self.total,
        }


@dataclass(frozen=True)
class ScenarioEffectsCubeResponseDTO:
    years: list[int]
    total_column_label: str
    unit: str
    group_by_label: str
    group_by_inner_label: str | None
    rows: list[CubeTableRowDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "years": self.years,
            "total_column_label": self.total_column_label,
            "unit": self.unit,
            "group_by_label": self.group_by_label,
            "group_by_inner_label": self.group_by_inner_label,
            "table": {"rows": [row.to_api_dict() for row in self.rows]},
        }
