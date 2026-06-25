from __future__ import annotations

from bisect import bisect_right
from decimal import Decimal
from typing import Iterable

from core.models import Route
from scenarios.domain.repositories.elasticity import (
    ElasticityRulePointRepository,
    ElasticityRuleRepository,
)
from scenarios.models import ElasticityRule, Scenario


RuleKey = tuple[int | None, int | None, int | None]
RuleIndex = dict[RuleKey, list[ElasticityRule]]
PointsIndex = dict[int, tuple[list[Decimal], list[Decimal]]]


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


def build_rule_index(rules: Iterable[ElasticityRule]) -> RuleIndex:
    """
    Индекс правил для быстрого выбора.

    Ключ: (cargo_group_id|None, cargo_id|None, message_type_id|None).
    Внутри списка правила уже отсортированы по (position, id) благодаря загрузке из репозитория.
    """
    index: RuleIndex = {}
    for rule in rules:
        key: RuleKey = (rule.cargo_group_id, rule.cargo_id, rule.message_type_id)
        index.setdefault(key, []).append(rule)
    return index


def _cargo_group_id_from_route_like(route: Route) -> int | None:
    if getattr(route, "cargo_id", None) is None:
        return None
    cargo = getattr(route, "cargo", None)
    if cargo is None:
        return None
    return getattr(cargo, "cargo_group_id", None)


def select_rule_for_route_indexed(route: Route, rule_index: RuleIndex) -> ElasticityRule | None:
    """
    Быстрый выбор правила с тем же приоритетом специфичности, что и `select_rule_for_route`.

    Порядок поиска (от наиболее специфичного к общему):
    (cg, c, mt) → (cg, c, None) → (cg, None, mt) → (None, c, mt) →
    (cg, None, None) → (None, c, None) → (None, None, mt) → (None, None, None)
    """
    cargo_group_id = _cargo_group_id_from_route_like(route)
    cargo_id = getattr(route, "cargo_id", None)
    message_type_id = getattr(route, "message_type_id", None)

    keys: tuple[RuleKey, ...] = (
        (cargo_group_id, cargo_id, message_type_id),
        (cargo_group_id, cargo_id, None),
        (cargo_group_id, None, message_type_id),
        (None, cargo_id, message_type_id),
        (cargo_group_id, None, None),
        (None, cargo_id, None),
        (None, None, message_type_id),
        (None, None, None),
    )
    for key in keys:
        rules = rule_index.get(key)
        if rules:
            return rules[0]
    return None


def marginality_ratio_from_percent(marginality_percent: Decimal) -> Decimal:
    """Конвертирует маржинальность из процентов (12.96) в долю (0.1296)."""
    return marginality_percent / Decimal("100")


def build_points_index(points_by_rule_id: dict[int, list]) -> PointsIndex:
    """
    Превращает точки правил в структуру для floor-lookup через bisect.

    points_by_rule_id: {rule_id: [ElasticityRulePoint,...]} (точки должны быть отсортированы).
    Возвращает: {rule_id: ([marginality...], [coefficient...])}
    """
    index: PointsIndex = {}
    for rule_id, points in points_by_rule_id.items():
        if not points:
            continue
        margs: list[Decimal] = []
        coefs: list[Decimal] = []
        for point in points:
            margs.append(point.marginality)
            coefs.append(point.coefficient)
        index[int(rule_id)] = (margs, coefs)
    return index


def _lookup_coefficient_from_points_index(
    rule_id: int,
    marginality_ratio: Decimal,
    points_index: PointsIndex,
) -> Decimal | None:
    packed = points_index.get(int(rule_id))
    if packed is None:
        return None
    margs, coefs = packed
    if not margs:
        return None
    pos = bisect_right(margs, marginality_ratio) - 1
    if pos < 0:
        return coefs[0]
    return coefs[pos]


def lookup_coefficient_for_marginality(
    rule: ElasticityRule,
    marginality_ratio: Decimal,
    *,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    if points_index is not None:
        value = _lookup_coefficient_from_points_index(
            rule.id,
            marginality_ratio,
            points_index,
        )
        if value is not None:
            return value

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

    coefficient = apply_enterprise_load_cap(
        coefficient,
        resolve_enterprise_load_coefficient(route),
        enabled=bool(scenario.consider_enterprise_load),
    )
    if coefficient is None:
        return None
    return max(Decimal("0"), coefficient)


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
    # Decimal('NaN') возможен при загрузке чисел из pandas/строк.
    try:
        if isinstance(enterprise_load, Decimal) and enterprise_load.is_nan():
            return coefficient
    except Exception:
        return coefficient
    if enterprise_load >= 1:
        return Decimal("1")
    cap = Decimal("1") + (Decimal("1") - enterprise_load)
    return min(coefficient, cap)
