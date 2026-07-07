from __future__ import annotations

from decimal import Decimal

from core.models import Route
from scenarios.domain.repositories.elasticity import (
    ElasticityRulePointRepository,
    ElasticityRuleRepository,
)
from scenarios.domain.utils.elasticity_matching import (
    compute_retention_at_tariff_change,
    select_rule_for_route,
)
from scenarios.models import Scenario

from .dto import RzdTariffSensitivityPointDTO, RzdTariffSensitivityResponseDTO

TARIFF_CHANGE_START = Decimal("-0.25")
TARIFF_CHANGE_END = Decimal("0.25")
TARIFF_CHANGE_STEP = Decimal("0.005")


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


def _iter_tariff_changes() -> list[Decimal]:
    values: list[Decimal] = []
    current = TARIFF_CHANGE_START
    while current <= TARIFF_CHANGE_END:
        values.append(current)
        current += TARIFF_CHANGE_STEP
    return values


def build_rzd_tariff_sensitivity(
    *,
    route: Route,
    scenario: Scenario,
) -> RzdTariffSensitivityResponseDTO:
    if not scenario.elasticity_set_id:
        return RzdTariffSensitivityResponseDTO(points=[])

    price = route.market_price_per_ton or Decimal("0")
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
        coefficient = compute_retention_at_tariff_change(
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
