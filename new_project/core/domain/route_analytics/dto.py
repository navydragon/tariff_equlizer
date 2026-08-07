from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from .dimensions import (
    INNER_DIMENSION_NONE,
    LOADING_BASE_YEAR,
    VALID_INNER_DIMENSIONS,
    VALID_KPI_YEARS,
    VALID_METRICS,
    get_dimension,
)


@dataclass(frozen=True)
class RouteAnalyticsRequestDTO:
    route_set_id: int
    dimension: str
    metric: str
    kpi_year: int = LOADING_BASE_YEAR
    dimension_inner: str = INNER_DIMENSION_NONE
    parent_filter: str | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.route_set_id, int) or self.route_set_id <= 0:
            errors.append("Некорректный route_set_id")
        if not get_dimension(self.dimension):
            errors.append("Некорректный параметр группировки")
        if self.metric not in VALID_METRICS:
            errors.append("Некорректная метрика")
        if self.kpi_year not in VALID_KPI_YEARS:
            errors.append("Некорректный kpi_year")
        if self.dimension_inner not in VALID_INNER_DIMENSIONS:
            errors.append("Некорректная группировка внутри")
        if (
            self.dimension_inner != INNER_DIMENSION_NONE
            and self.dimension_inner == self.dimension
        ):
            errors.append("Группировка внутри не может совпадать с параметром группировки")
        if self.parent_filter is not None and self.dimension_inner == INNER_DIMENSION_NONE:
            errors.append("parent_filter недоступен без группировки внутри")
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
    dimension_inner: str = INNER_DIMENSION_NONE
    dimension_inner_label: str | None = None
    drilldown_enabled: bool = False
    parent_filter: str | None = None
    parent_label: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_api_dict() for row in self.rows],
            "total": float(self.total),
            "total_display": self.total_display,
            "metric": self.metric,
            "unit": self.unit,
            "dimension": self.dimension,
            "dimension_label": self.dimension_label,
            "dimension_inner": self.dimension_inner,
            "dimension_inner_label": self.dimension_inner_label,
            "drilldown_enabled": self.drilldown_enabled,
            "parent_filter": self.parent_filter,
            "parent_label": self.parent_label,
        }


@dataclass(frozen=True)
class RouteAnalyticsNestedRowDTO:
    outer_label: str
    inner_label: str
    value: Decimal
    value_display: str
    share_pct: str
    is_subtotal: bool = False
    is_total: bool = False

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "outer_label": self.outer_label,
            "inner_label": self.inner_label,
            "value": float(self.value),
            "value_display": self.value_display,
            "share_pct": self.share_pct,
            "is_subtotal": self.is_subtotal,
            "is_total": self.is_total,
        }


@dataclass(frozen=True)
class RouteAnalyticsNestedResultDTO:
    rows: list[RouteAnalyticsNestedRowDTO]
    total: Decimal
    total_display: str
    metric: str
    unit: str
    dimension: str
    dimension_label: str
    dimension_inner: str
    dimension_inner_label: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "rows": [row.to_api_dict() for row in self.rows],
            "total": float(self.total),
            "total_display": self.total_display,
            "metric": self.metric,
            "unit": self.unit,
            "dimension": self.dimension,
            "dimension_label": self.dimension_label,
            "dimension_inner": self.dimension_inner,
            "dimension_inner_label": self.dimension_inner_label,
            "nested": True,
        }


METRIC_LABELS: dict[str, str] = {
    "count": "Количество",
    "money": "Доходы",
    "volume": "Погрузка",
    "turnover": "Грузооборот",
}


@dataclass(frozen=True)
class RouteSetTotalCardDTO:
    metric: str
    label: str
    value: Decimal
    value_display: str
    unit: str

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "metric": self.metric,
            "label": self.label,
            "value": float(self.value),
            "value_display": self.value_display,
            "unit": self.unit,
        }


@dataclass(frozen=True)
class RouteSetTotalsDTO:
    route_set_id: int
    route_set_code: str
    route_set_name: str
    cards: list[RouteSetTotalCardDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "route_set": {
                "id": self.route_set_id,
                "code": self.route_set_code,
                "name": self.route_set_name,
            },
            "cards": [card.to_api_dict() for card in self.cards],
        }
