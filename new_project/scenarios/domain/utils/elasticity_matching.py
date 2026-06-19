from __future__ import annotations

from decimal import Decimal

from core.models import Route
from scenarios.domain.repositories.elasticity import (
    ElasticityRulePointRepository,
    ElasticityRuleRepository,
)
from scenarios.models import ElasticityRule, Scenario


def rule_specificity(rule: ElasticityRule) -> int:
    return sum(
        1
        for value in (
            rule.cargo_group_id,
            rule.cargo_id,
            rule.message_type_id,
        )
        if value is not None
    )


def rule_matches_route(route: Route, rule: ElasticityRule) -> bool:
    if rule.cargo_group_id is not None:
        cargo_group_id = (
            route.cargo.cargo_group_id if route.cargo_id else None
        )
        if cargo_group_id != rule.cargo_group_id:
            return False
    if rule.cargo_id is not None and route.cargo_id != rule.cargo_id:
        return False
    if rule.message_type_id is not None:
        if route.message_type_id != rule.message_type_id:
            return False
    return True


def select_rule_for_route(
    route: Route,
    rules: list[ElasticityRule],
) -> ElasticityRule | None:
    matched = [rule for rule in rules if rule_matches_route(route, rule)]
    if not matched:
        return None
    return min(
        matched,
        key=lambda rule: (-rule_specificity(rule), rule.position, rule.id),
    )


def marginality_ratio_from_percent(marginality_percent: Decimal) -> Decimal:
    """Конвертирует маржинальность из процентов (12.96) в долю (0.1296)."""
    return marginality_percent / Decimal("100")


def lookup_coefficient_for_marginality(
    rule: ElasticityRule,
    marginality_ratio: Decimal,
    *,
    point_repo: ElasticityRulePointRepository | None = None,
) -> Decimal | None:
    repo = point_repo or ElasticityRulePointRepository()
    point = repo.find_floor_point(rule.id, marginality_ratio)
    if point is None:
        points = repo.list_by_rule(rule.id)
        if not points:
            return None
        point = points[0]
    return point.coefficient


def resolve_retention_coefficient(
    route: Route,
    scenario: Scenario,
    marginality_ratio: Decimal,
    *,
    rule_repo: ElasticityRuleRepository | None = None,
    point_repo: ElasticityRulePointRepository | None = None,
) -> Decimal | None:
    if not scenario.elasticity_set_id:
        return None

    rules = (rule_repo or ElasticityRuleRepository()).list_by_set(
        scenario.elasticity_set_id,
    )
    rule = select_rule_for_route(route, rules)
    if rule is None:
        return None

    return lookup_coefficient_for_marginality(
        rule,
        marginality_ratio,
        point_repo=point_repo,
    )


def _route_cost_baseline(route: Route) -> Decimal:
    production_cost = route.production_cost_per_ton
    total_cost = route.total_cost_per_ton
    if production_cost is not None:
        return production_cost
    if total_cost is not None:
        return total_cost
    return Decimal("0")


def _to_decimal_or_zero(value: Decimal | None) -> Decimal:
    return value if value is not None else Decimal("0")


def route_base_marginality_ratio(route: Route) -> Decimal:
    """Маржинальность маршрута по полям БД без сценарных изменений."""
    price = _to_decimal_or_zero(route.market_price_per_ton)
    if price <= 0:
        return Decimal("0")
    cost = _route_cost_baseline(route)
    rzd = _to_decimal_or_zero(route.rzd_cost_total_per_ton)
    oper = _to_decimal_or_zero(route.operators_cost_per_ton)
    per = _to_decimal_or_zero(route.transshipment_cost_per_ton)
    marginality_rub = price - cost - rzd - oper - per
    return marginality_rub / price


def compute_retention_coefficient(
    route: Route,
    scenario: Scenario,
    current_marginality_ratio: Decimal,
    *,
    rule_repo: ElasticityRuleRepository | None = None,
    point_repo: ElasticityRulePointRepository | None = None,
) -> Decimal | None:
    if not scenario.elasticity_set_id:
        return None

    rules = (rule_repo or ElasticityRuleRepository()).list_by_set(
        scenario.elasticity_set_id,
    )
    rule = select_rule_for_route(route, rules)
    if rule is None:
        return None

    repo = point_repo or ElasticityRulePointRepository()
    current_coefficient = lookup_coefficient_for_marginality(
        rule,
        current_marginality_ratio,
        point_repo=repo,
    )
    if current_coefficient is None:
        return None

    mode = scenario.retention_coefficient_mode
    if mode == Scenario.RetentionCoefficientMode.RELATIVE_TO_BASE:
        base_marginality = route_base_marginality_ratio(route)
        base_coefficient = lookup_coefficient_for_marginality(
            rule,
            base_marginality,
            point_repo=repo,
        )
        if base_coefficient is None:
            return None
        coefficient = Decimal("1") + current_coefficient - base_coefficient
    else:
        coefficient = current_coefficient

    return apply_enterprise_load_cap(
        coefficient,
        resolve_enterprise_load_coefficient(route),
        enabled=bool(scenario.consider_enterprise_load),
    )


def resolve_enterprise_load_coefficient(route: Route) -> Decimal | None:
    own = route.enterprise_load_coefficient
    if own is not None and own != 0:
        return own
    model_route = getattr(route, "model_route", None)
    if model_route is None:
        return None
    model_val = model_route.enterprise_load_coefficient
    if model_val is None or model_val == 0:
        return None
    return model_val


def apply_enterprise_load_cap(
    coefficient: Decimal | None,
    enterprise_load: Decimal | None,
    *,
    enabled: bool,
) -> Decimal | None:
    if coefficient is None or not enabled:
        return coefficient
    if enterprise_load is None or enterprise_load == 0:
        return coefficient
    if enterprise_load >= 1:
        return Decimal("1")
    cap = Decimal("1") + (Decimal("1") - enterprise_load)
    return min(coefficient, cap)
