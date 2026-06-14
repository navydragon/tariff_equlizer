from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .dimensions import VALID_METRICS, get_dimension


@dataclass(frozen=True)
class RouteAnalyticsRequestDTO:
    route_set_id: int
    dimension: str
    metric: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.route_set_id, int) or self.route_set_id <= 0:
            errors.append("Некорректный route_set_id")
        if not get_dimension(self.dimension):
            errors.append("Некорректный параметр группировки")
        if self.metric not in VALID_METRICS:
            errors.append("Некорректная метрика")
        return errors


@dataclass(frozen=True)
class RouteAnalyticsRowDTO:
    label: str
    value: Decimal
    value_display: str
    share_pct: str
    is_total: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "value": float(self.value),
            "value_display": self.value_display,
            "share_pct": self.share_pct,
            "is_total": self.is_total,
        }


@dataclass(frozen=True)
class RouteAnalyticsResultDTO:
    rows: list[RouteAnalyticsRowDTO]
    total: Decimal
    total_display: str
    metric: str
    unit: str
    dimension: str
    dimension_label: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_api_dict() for row in self.rows],
            "total": float(self.total),
            "total_display": self.total_display,
            "metric": self.metric,
            "unit": self.unit,
            "dimension": self.dimension,
            "dimension_label": self.dimension_label,
        }
