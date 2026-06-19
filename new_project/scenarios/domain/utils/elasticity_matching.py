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
