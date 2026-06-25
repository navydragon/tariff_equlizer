from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from calculations.domain.constants import (
    EFFECTS_GROUP_BY_CHOICES,
    EFFECTS_GROUP_BY_INNER_CHOICES,
)
from core.domain.cargo.ordering import normalize_filter_options

GROUP_BY_CHOICES = EFFECTS_GROUP_BY_CHOICES
GROUP_BY_INNER_CHOICES = EFFECTS_GROUP_BY_INNER_CHOICES


@dataclass(frozen=True)
class ScenarioEffectsComputeRequestDTO:
    scenario_id: int
    include_rule_breakdown: bool = False

    def validate(self) -> list[str]:
        if not isinstance(self.scenario_id, int) or self.scenario_id <= 0:
            return ["Некорректный scenario_id"]
        return []


@dataclass(frozen=True)
class ScenarioEffectsAggregateRequestDTO:
    cache_key: str
    year: int
    group_by: str = "cargo_group"
    group_by_inner: str = "none"
    cargo_groups: list[str] = field(default_factory=list)
    holdings: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.cache_key or not isinstance(self.cache_key, str):
            errors.append("Некорректный cache_key")
        if not isinstance(self.year, int):
            errors.append("Некорректный year")
        if self.group_by not in GROUP_BY_CHOICES:
            errors.append("Некорректный group_by")
        if self.group_by_inner not in GROUP_BY_INNER_CHOICES:
            errors.append("Некорректный group_by_inner")
        if self.group_by_inner != "none" and self.group_by_inner == self.group_by:
            errors.append("group_by_inner не может совпадать с group_by")
        if not isinstance(self.cargo_groups, list):
            errors.append("cargo_groups должен быть списком")
        if not isinstance(self.holdings, list):
            errors.append("holdings должен быть списком")
        return errors


# Сохранён для обратной совместимости тестов.
@dataclass(frozen=True)
class ScenarioEffectsRequestDTO:
    scenario_id: int
    year: int
    group_by: str = "cargo_group"
    group_by_inner: str = "none"
    cargo_groups: list[str] = field(default_factory=list)
    holdings: list[str] = field(default_factory=list)

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.scenario_id, int) or self.scenario_id <= 0:
            errors.append("Некорректный scenario_id")
        if not isinstance(self.year, int):
            errors.append("Некорректный year")
        if self.group_by not in GROUP_BY_CHOICES:
            errors.append("Некорректный group_by")
        if self.group_by_inner not in GROUP_BY_INNER_CHOICES:
            errors.append("Некорректный group_by_inner")
        if self.group_by_inner != "none" and self.group_by_inner == self.group_by:
            errors.append("group_by_inner не может совпадать с group_by")
        if not isinstance(self.cargo_groups, list):
            errors.append("cargo_groups должен быть списком")
        if not isinstance(self.holdings, list):
            errors.append("holdings должен быть списком")
        return errors


@dataclass(frozen=True)
class EffectKpiCardDTO:
    year: int
    total_bln: str
    total_pct: str
    base_bln: str
    base_pct: str
    rules_bln: str
    rules_pct: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "total_bln": self.total_bln,
            "total_pct": self.total_pct,
            "base_bln": self.base_bln,
            "base_pct": self.base_pct,
            "rules_bln": self.rules_bln,
            "rules_pct": self.rules_pct,
        }


@dataclass(frozen=True)
class EffectTableRowDTO:
    label: str
    is_subtotal: bool
    base_rub: str
    base_pct: str
    rules_rub: str
    rules_pct: str
    total_rub: str
    total_pct: str
    row_kind: str = "tariff"
    volume_mln_t: str | None = None
    volume_pct: str | None = None
    fallout_bln: str | None = None
    fallout_volume_mln_t: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload = {
            "label": self.label,
            "is_subtotal": self.is_subtotal,
            "base_rub": self.base_rub,
            "base_pct": self.base_pct,
            "rules_rub": self.rules_rub,
            "rules_pct": self.rules_pct,
            "total_rub": self.total_rub,
            "total_pct": self.total_pct,
            "row_kind": self.row_kind,
        }
        if self.volume_mln_t is not None:
            payload["volume_mln_t"] = self.volume_mln_t
        if self.volume_pct is not None:
            payload["volume_pct"] = self.volume_pct
        if self.fallout_bln is not None:
            payload["fallout_bln"] = self.fallout_bln
        if self.fallout_volume_mln_t is not None:
            payload["fallout_volume_mln_t"] = self.fallout_volume_mln_t
        return payload


@dataclass(frozen=True)
class EffectChartDTO:
    labels: list[str]
    base_bln: list[str]
    rules_bln: list[str]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "labels": self.labels,
            "base_bln": self.base_bln,
            "rules_bln": self.rules_bln,
        }


@dataclass(frozen=True)
class ScenarioEffectsComputeResponseDTO:
    cache_key: str
    scenario_id: int
    years: list[int]
    baseline_rub: str
    routes_without_charge: int
    routes_without_volume: int
    cards: list[EffectKpiCardDTO]
    filter_options: dict[str, list[str]]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "cache_key": self.cache_key,
            "scenario_id": self.scenario_id,
            "years": self.years,
            "baseline_rub": self.baseline_rub,
            "routes_without_charge": self.routes_without_charge,
            "routes_without_volume": self.routes_without_volume,
            "cards": [card.to_api_dict() for card in self.cards],
            "filter_options": normalize_filter_options(self.filter_options),
        }


@dataclass(frozen=True)
class ScenarioEffectsAggregateResponseDTO:
    table_rows: list[EffectTableRowDTO]
    chart: EffectChartDTO
    show_fallout_column: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        payload = {
            "table": {
                "rows": [row.to_api_dict() for row in self.table_rows],
                "show_fallout": self.show_fallout_column,
            },
            "chart": self.chart.to_api_dict(),
        }
        return payload


@dataclass(frozen=True)
class ScenarioEffectsResponseDTO:
    scenario_id: int
    years: list[int]
    baseline_rub: str
    routes_without_charge: int
    cards: list[EffectKpiCardDTO]
    filter_options: dict[str, list[str]]
    table_rows: list[EffectTableRowDTO]
    chart: EffectChartDTO

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "years": self.years,
            "baseline_rub": self.baseline_rub,
            "routes_without_charge": self.routes_without_charge,
            "cards": [card.to_api_dict() for card in self.cards],
            "filter_options": normalize_filter_options(self.filter_options),
            "table": {"rows": [row.to_api_dict() for row in self.table_rows]},
            "chart": self.chart.to_api_dict(),
        }
