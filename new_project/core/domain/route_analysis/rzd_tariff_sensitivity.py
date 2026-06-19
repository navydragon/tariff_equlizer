from __future__ import annotations

from decimal import Decimal

from core.models import Route
from scenarios.domain.repositories.elasticity import (
    ElasticityRulePointRepository,
    ElasticityRuleRepository,
)
from scenarios.domain.utils.elasticity_matching import (
    apply_enterprise_load_cap,
    lookup_coefficient_for_marginality,
    resolve_enterprise_load_coefficient,
    route_base_marginality_ratio,
    select_rule_for_route,
)
from scenarios.models import ElasticityRule, Scenario

from .dto import RzdTariffSensitivityPointDTO, RzdTariffSensitivityResponseDTO

TARIFF_CHANGE_START = Decimal("-0.25")
TARIFF_CHANGE_END = Decimal("0.25")
TARIFF_CHANGE_STEP = Decimal("0.005")
POSITIVE_TARIFF_SMOOTHING_STEP = Decimal("0.05")


def _to_decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def _route_cost_baseline(route: Route) -> Decimal:
    production_cost = route.production_cost_per_ton
    total_cost = route.total_cost_per_ton
    if production_cost is not None:
        return production_cost
    if total_cost is not None:
        return total_cost
    return Decimal("0")


def _quantize_coefficient(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _format_coefficient(value: Decimal) -> str:
    return format(_quantize_coefficient(value), "f")


def _format_change_pct(delta: Decimal) -> str:
    pct = (delta * Decimal("100")).quantize(Decimal("0.1"))
    text = format(pct, "f")
    if "." in text:
        text = text.rstrip("0").rstrip(".")
    return text


def _marginality_ratio_for_tariff_change(
    route: Route,
    tariff_change: Decimal,
) -> Decimal:
    price = _to_decimal_or_zero(route.market_price_per_ton)
    if price <= 0:
        return Decimal("0")
    cost = _route_cost_baseline(route)
    rzd_base = _to_decimal_or_zero(route.rzd_cost_total_per_ton)
    oper = _to_decimal_or_zero(route.operators_cost_per_ton)
    per = _to_decimal_or_zero(route.transshipment_cost_per_ton)
    rzd = rzd_base * (Decimal("1") + tariff_change)
    marginality_rub = price - cost - rzd - oper - per
    return marginality_rub / price


def _iter_tariff_changes() -> list[Decimal]:
    values: list[Decimal] = []
    current = TARIFF_CHANGE_START
    while current <= TARIFF_CHANGE_END:
        values.append(current)
        current += TARIFF_CHANGE_STEP
    return values


def _ipem_coefficient_for_tariff_change(
    *,
    route: Route,
    scenario: Scenario,
    tariff_change: Decimal,
    previous_coefficient: Decimal | None,
    rule: ElasticityRule,
    point_repo: ElasticityRulePointRepository,
) -> Decimal | None:
    margin = _marginality_ratio_for_tariff_change(route, tariff_change)
    current_lookup = lookup_coefficient_for_marginality(
        rule,
        margin,
        point_repo=point_repo,
    )
    if current_lookup is None:
        return None

    if tariff_change > 0:
        previous = (
            previous_coefficient
            if previous_coefficient is not None
            else Decimal("1")
        )
        return min(
            Decimal("1"),
            max(current_lookup, previous - POSITIVE_TARIFF_SMOOTHING_STEP),
        )

    if tariff_change == 0:
        return Decimal("1")

    enterprise_load = resolve_enterprise_load_coefficient(route)
    if enterprise_load is not None and enterprise_load >= 1:
        return Decimal("1")

    base_margin = route_base_marginality_ratio(route)
    base_lookup = lookup_coefficient_for_marginality(
        rule,
        base_margin,
        point_repo=point_repo,
    )
    if base_lookup is None:
        return None

    coefficient = Decimal("1") + current_lookup - base_lookup
    return apply_enterprise_load_cap(
        coefficient,
        enterprise_load,
        enabled=bool(scenario.consider_enterprise_load),
    )


def build_rzd_tariff_sensitivity(
    *,
    route: Route,
    scenario: Scenario,
) -> RzdTariffSensitivityResponseDTO:
    if not scenario.elasticity_set_id:
        return RzdTariffSensitivityResponseDTO(points=[])

    price = _to_decimal_or_zero(route.market_price_per_ton)
    if price <= 0:
        return RzdTariffSensitivityResponseDTO(points=[])

    rules = ElasticityRuleRepository().list_by_set(scenario.elasticity_set_id)
    rule = select_rule_for_route(route, rules)
    if rule is None:
        return RzdTariffSensitivityResponseDTO(points=[])

    point_repo = ElasticityRulePointRepository()
    points: list[RzdTariffSensitivityPointDTO] = []
    previous_coefficient: Decimal | None = None

    for tariff_change in _iter_tariff_changes():
        coefficient = _ipem_coefficient_for_tariff_change(
            route=route,
            scenario=scenario,
            tariff_change=tariff_change,
            previous_coefficient=previous_coefficient,
            rule=rule,
            point_repo=point_repo,
        )
        points.append(
            RzdTariffSensitivityPointDTO(
                change_pct=_format_change_pct(tariff_change),
                coefficient=(
                    _format_coefficient(coefficient)
                    if coefficient is not None
                    else None
                ),
            ),
        )
        if coefficient is not None:
            previous_coefficient = coefficient

    if all(point.coefficient is None for point in points):
        return RzdTariffSensitivityResponseDTO(points=[])

    return RzdTariffSensitivityResponseDTO(points=points)
