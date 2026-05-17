from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal
from typing import Any


@dataclass(frozen=True)
class TariffLoadRequestDTO:
    scenario_id: int
    route_ids: list[int]

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.scenario_id, int) or self.scenario_id <= 0:
            errors.append("Некорректный scenario_id")
        if not isinstance(self.route_ids, list) or not self.route_ids:
            errors.append("route_ids должен быть непустым списком")
        elif any(not isinstance(rid, int) or rid <= 0 for rid in self.route_ids):
            errors.append("Некорректный route_id в списке")
        return errors


@dataclass(frozen=True)
class TariffLoadByYearDTO:
    total: dict[int, Decimal] = field(default_factory=dict)
    base: dict[int, Decimal] = field(default_factory=dict)
    rules: dict[int, Decimal] = field(default_factory=dict)


@dataclass(frozen=True)
class TariffRuleEffectDTO:
    rule_id: int
    name: str
    load_by_year: dict[int, Decimal]

    @property
    def total_load(self) -> Decimal:
        return sum(self.load_by_year.values(), Decimal("0"))


@dataclass(frozen=True)
class RouteTariffLoadDTO:
    route_id: int
    route_code: str
    years: list[int]
    rzd_by_year: dict[int, Decimal]
    rzd_loaded_by_year: dict[int, Decimal]
    rzd_empty_by_year: dict[int, Decimal]
    base_coefficient_by_year: dict[int, Decimal]
    rules_coefficient_by_year: dict[int, Decimal]
    tariff_load: TariffLoadByYearDTO
    rule_effects: list[TariffRuleEffectDTO] = field(default_factory=list)

    def to_api_dict(self) -> dict[str, Any]:
        def year_map(data: dict[int, Decimal]) -> dict[str, str]:
            return {str(year): format(value, "f") for year, value in data.items()}

        return {
            "route_id": self.route_id,
            "route_code": self.route_code,
            "years": self.years,
            "rzd_by_year": year_map(self.rzd_by_year),
            "rzd_loaded_by_year": year_map(self.rzd_loaded_by_year),
            "rzd_empty_by_year": year_map(self.rzd_empty_by_year),
            "base_coefficient_by_year": year_map(self.base_coefficient_by_year),
            "rules_coefficient_by_year": year_map(self.rules_coefficient_by_year),
            "tariff_load": {
                "total": year_map(self.tariff_load.total),
                "base": year_map(self.tariff_load.base),
                "rules": year_map(self.tariff_load.rules),
            },
            "rule_effects": [
                {
                    "rule_id": effect.rule_id,
                    "name": effect.name,
                    "load_by_year": year_map(effect.load_by_year),
                }
                for effect in self.rule_effects
            ],
        }


@dataclass(frozen=True)
class TariffLoadResponseDTO:
    scenario_id: int
    routes: list[RouteTariffLoadDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "routes": [route.to_api_dict() for route in self.routes],
        }
