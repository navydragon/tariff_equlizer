from __future__ import annotations

from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class CalculateRouteRequestDTO:
    scenario_id: int
    route_id: int

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.scenario_id, int) or self.scenario_id <= 0:
            errors.append("Некорректный scenario_id")
        if not isinstance(self.route_id, int) or self.route_id <= 0:
            errors.append("Некорректный route_id")
        return errors


@dataclass(frozen=True)
class CalculateRouteTableRowDTO:
    key: str
    label: str
    values: Any
    format: str


@dataclass(frozen=True)
class CalculateRouteResponseDTO:
    scenario_id: int
    route_id: int
    route_code: str
    years: list[int]
    rows: list[CalculateRouteTableRowDTO]
