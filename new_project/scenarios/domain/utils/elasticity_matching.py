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

TARIFF_CHANGE_STEP = Decimal("0.005")
POSITIVE_TARIFF_SMOOTHING_STEP = Decimal("0.05")
TARIFF_CHANGE_STEP_FLOAT = 0.005
POSITIVE_TARIFF_SMOOTHING_STEP_FLOAT = 0.05


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


def select_rule_for_keys_indexed(
    rule_index: RuleIndex,
    *,
    cargo_group_id: int | None,
    cargo_id: int | None,
    message_type_id: int | None,
) -> ElasticityRule | None:
    """Быстрый выбор правила по id полям (без Route/proxy)."""
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


FloatPointsIndex = dict[int, tuple[list[float], list[float]]]


def build_float_points_index(points_index: PointsIndex) -> FloatPointsIndex:
    """Конвертирует точки правил в float для hot path fallout."""
    index: FloatPointsIndex = {}
    for rule_id, (margs, coefs) in points_index.items():
        index[int(rule_id)] = (
            [float(m) for m in margs],
            [float(c) for c in coefs],
        )
    return index


def lookup_coefficient_for_marginality_float(
    rule_id: int,
    marginality_ratio: float,
    points_index: FloatPointsIndex,
) -> float | None:
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


def apply_enterprise_load_cap_float(
    coefficient: float | None,
    enterprise_load: float,
    *,
    enabled: bool,
) -> float | None:
    if coefficient is None or not enabled:
        return coefficient
    if enterprise_load == 0.0 or enterprise_load != enterprise_load:
        return coefficient
    if enterprise_load >= 1.0:
        return 1.0
    cap = 1.0 + (1.0 - enterprise_load)
    return min(coefficient, cap)


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


def marginality_ratio_for_tariff_change(
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


def _iter_tariff_change_steps(tariff_change_target: Decimal) -> list[Decimal]:
    if tariff_change_target == 0:
        return []
    step = TARIFF_CHANGE_STEP
    steps: list[Decimal] = []
    current = Decimal("0")
    if tariff_change_target > 0:
        while current < tariff_change_target:
            current += step
            if current > tariff_change_target:
                current = tariff_change_target
            steps.append(current)
    else:
        while current > tariff_change_target:
            current -= step
            if current < tariff_change_target:
                current = tariff_change_target
            steps.append(current)
    return steps


def compute_retention_at_tariff_change(
    *,
    route: Route,
    scenario: Scenario,
    tariff_change: Decimal,
    previous_coefficient: Decimal | None,
    rule: ElasticityRule,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    fixed = resolve_fixed_retention_coefficient(route)
    if fixed is not None:
        return fixed

    margin = marginality_ratio_for_tariff_change(route, tariff_change)
    current_lookup = lookup_coefficient_for_marginality(
        rule,
        margin,
        point_repo=point_repo,
        points_index=points_index,
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
        points_index=points_index,
    )
    if base_lookup is None:
        return None

    coefficient = Decimal("1") + current_lookup - base_lookup
    return apply_enterprise_load_cap(
        coefficient,
        enterprise_load,
        enabled=bool(scenario.consider_enterprise_load),
    )


def compute_retention_at_charge_ratio(
    route: Route,
    scenario: Scenario,
    charge_ratio: Decimal,
    *,
    rule_repo: ElasticityRuleRepository | None = None,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    if not scenario.elasticity_set_id:
        return None

    fixed = resolve_fixed_retention_coefficient(route)
    if fixed is not None:
        return max(Decimal("0"), fixed)

    rules = (rule_repo or ElasticityRuleRepository()).list_by_set(
        scenario.elasticity_set_id,
    )
    rule = select_rule_for_route(route, rules)
    if rule is None:
        return None

    tariff_change_target = charge_ratio - Decimal("1")
    if tariff_change_target == 0:
        return Decimal("1")

    repo = point_repo or ElasticityRulePointRepository()
    previous_coefficient: Decimal | None = None
    for tariff_change in _iter_tariff_change_steps(tariff_change_target):
        previous_coefficient = compute_retention_at_tariff_change(
            route=route,
            scenario=scenario,
            tariff_change=tariff_change,
            previous_coefficient=previous_coefficient,
            rule=rule,
            point_repo=repo,
            points_index=points_index,
        )
        if previous_coefficient is None:
            return None

    if previous_coefficient is None:
        return None
    return max(Decimal("0"), previous_coefficient)


def compute_retention_at_tariff_change_from_margin(
    *,
    scenario: Scenario,
    tariff_change: Decimal,
    previous_coefficient: Decimal | None,
    margin: Decimal,
    base_margin: Decimal,
    rule: ElasticityRule,
    enterprise_load: Decimal | None,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    current_lookup = lookup_coefficient_for_marginality(
        rule,
        margin,
        point_repo=point_repo,
        points_index=points_index,
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

    if enterprise_load is not None and enterprise_load >= 1:
        return Decimal("1")

    base_lookup = lookup_coefficient_for_marginality(
        rule,
        base_margin,
        point_repo=point_repo,
        points_index=points_index,
    )
    if base_lookup is None:
        return None

    coefficient = Decimal("1") + current_lookup - base_lookup
    return apply_enterprise_load_cap(
        coefficient,
        enterprise_load,
        enabled=bool(scenario.consider_enterprise_load),
    )


def compute_retention_at_charge_ratio_from_margin(
    *,
    charge_ratio: Decimal,
    margin_fn,
    base_margin: Decimal,
    rule: ElasticityRule,
    enterprise_load: Decimal | None,
    scenario: Scenario,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    tariff_change_target = charge_ratio - Decimal("1")
    if tariff_change_target == 0:
        return Decimal("1")

    repo = point_repo or ElasticityRulePointRepository()
    previous_coefficient: Decimal | None = None
    for tariff_change in _iter_tariff_change_steps(tariff_change_target):
        margin = margin_fn(tariff_change)
        previous_coefficient = compute_retention_at_tariff_change_from_margin(
            scenario=scenario,
            tariff_change=tariff_change,
            previous_coefficient=previous_coefficient,
            margin=margin,
            base_margin=base_margin,
            rule=rule,
            enterprise_load=enterprise_load,
            point_repo=repo,
            points_index=points_index,
        )
        if previous_coefficient is None:
            return None

    if previous_coefficient is None:
        return None
    return max(Decimal("0"), previous_coefficient)


def _iter_tariff_change_steps_float(tariff_change_target: float) -> list[float]:
    if tariff_change_target == 0.0:
        return []
    step = TARIFF_CHANGE_STEP_FLOAT
    steps: list[float] = []
    current = 0.0
    if tariff_change_target > 0.0:
        while current < tariff_change_target:
            current += step
            if current > tariff_change_target:
                current = tariff_change_target
            steps.append(current)
    else:
        while current > tariff_change_target:
            current -= step
            if current < tariff_change_target:
                current = tariff_change_target
            steps.append(current)
    return steps


def compute_retention_at_tariff_change_float(
    *,
    tariff_change: float,
    previous_coefficient: float | None,
    margin: float,
    base_margin: float,
    rule_id: int,
    enterprise: float,
    scenario: Scenario,
    float_points_index: FloatPointsIndex,
) -> float | None:
    current_lookup = lookup_coefficient_for_marginality_float(
        rule_id,
        margin,
        float_points_index,
    )
    if current_lookup is None:
        return None

    if tariff_change > 0.0:
        previous = (
            previous_coefficient
            if previous_coefficient is not None
            else 1.0
        )
        return min(
            1.0,
            max(current_lookup, previous - POSITIVE_TARIFF_SMOOTHING_STEP_FLOAT),
        )

    if tariff_change == 0.0:
        return 1.0

    if enterprise >= 1.0:
        return 1.0

    base_lookup = lookup_coefficient_for_marginality_float(
        rule_id,
        base_margin,
        float_points_index,
    )
    if base_lookup is None:
        return None

    coefficient = 1.0 + current_lookup - base_lookup
    return apply_enterprise_load_cap_float(
        coefficient,
        enterprise,
        enabled=bool(scenario.consider_enterprise_load),
    )


def compute_retention_at_charge_ratio_float(
    *,
    charge_ratio: float,
    margin_fn,
    base_margin: float,
    rule_id: int,
    enterprise: float,
    scenario: Scenario,
    float_points_index: FloatPointsIndex,
) -> float | None:
    tariff_change_target = charge_ratio - 1.0
    if tariff_change_target == 0.0:
        return 1.0

    previous_coefficient: float | None = None
    for tariff_change in _iter_tariff_change_steps_float(tariff_change_target):
        margin = margin_fn(tariff_change)
        previous_coefficient = compute_retention_at_tariff_change_float(
            tariff_change=tariff_change,
            previous_coefficient=previous_coefficient,
            margin=margin,
            base_margin=base_margin,
            rule_id=rule_id,
            enterprise=enterprise,
            scenario=scenario,
            float_points_index=float_points_index,
        )
        if previous_coefficient is None:
            return None

    if previous_coefficient is None:
        return None
    return max(0.0, previous_coefficient)


def compute_retention_coefficient(
    route: Route,
    scenario: Scenario,
    current_marginality_ratio: Decimal,
    *,
    charge_ratio: Decimal | None = None,
    rule_repo: ElasticityRuleRepository | None = None,
    point_repo: ElasticityRulePointRepository | None = None,
    points_index: PointsIndex | None = None,
) -> Decimal | None:
    if not scenario.elasticity_set_id:
        return None

    fixed = resolve_fixed_retention_coefficient(route)
    if fixed is not None:
        return max(Decimal("0"), fixed)

    mode = scenario.retention_coefficient_mode
    if mode == Scenario.RetentionCoefficientMode.COMBINED:
        if charge_ratio is None:
            charge_ratio = Decimal("1")
        return compute_retention_at_charge_ratio(
            route,
            scenario,
            charge_ratio,
            rule_repo=rule_repo,
            point_repo=point_repo,
            points_index=points_index,
        )

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
        points_index=points_index,
    )
    if current_coefficient is None:
        return None

    if mode == Scenario.RetentionCoefficientMode.RELATIVE_TO_BASE:
        base_marginality = route_base_marginality_ratio(route)
        base_coefficient = lookup_coefficient_for_marginality(
            rule,
            base_marginality,
            point_repo=repo,
            points_index=points_index,
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


def resolve_fixed_retention_coefficient(route: Route) -> Decimal | None:
    own = getattr(route, "fixed_retention_coefficient", None)
    if own is not None and own != 0:
        return own
    model_route = getattr(route, "model_route", None)
    if model_route is None:
        return None
    model_val = getattr(model_route, "fixed_retention_coefficient", None)
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
