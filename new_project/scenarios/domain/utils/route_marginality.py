from __future__ import annotations

from decimal import Decimal

from core.models import Route


def _to_float(value: Decimal | float | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def route_cost_baseline(route: Route) -> float:
    production_cost = route.production_cost_per_ton
    total_cost = route.total_cost_per_ton
    if production_cost is not None:
        return _to_float(production_cost)
    if total_cost is not None:
        return _to_float(total_cost)
    return 0.0


def route_marginality_ratio_from_fields(
    *,
    market_price_per_ton: float,
    production_cost_per_ton: float,
    total_cost_per_ton: float,
    rzd_cost_total_per_ton: float,
    operators_cost_per_ton: float,
    transshipment_cost_per_ton: float,
) -> float:
    price = market_price_per_ton
    if price <= 0:
        return 0.0
    cost = (
        production_cost_per_ton
        if production_cost_per_ton > 0
        else total_cost_per_ton
    )
    margin_rub = (
        price
        - cost
        - rzd_cost_total_per_ton
        - operators_cost_per_ton
        - transshipment_cost_per_ton
    )
    return margin_rub / price


def route_marginality_ratio(route: Route, *, rzd_per_ton: float | None = None) -> float:
    rzd = (
        rzd_per_ton
        if rzd_per_ton is not None
        else _to_float(route.rzd_cost_total_per_ton)
    )
    return route_marginality_ratio_from_fields(
        market_price_per_ton=_to_float(route.market_price_per_ton),
        production_cost_per_ton=_to_float(route.production_cost_per_ton),
        total_cost_per_ton=_to_float(route.total_cost_per_ton),
        rzd_cost_total_per_ton=rzd,
        operators_cost_per_ton=_to_float(route.operators_cost_per_ton),
        transshipment_cost_per_ton=_to_float(route.transshipment_cost_per_ton),
    )


def route_base_marginality_ratio(route: Route) -> float:
    return route_marginality_ratio(route)
