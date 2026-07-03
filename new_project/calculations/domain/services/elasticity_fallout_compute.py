from __future__ import annotations

import logging
from dataclasses import dataclass
from decimal import Decimal

import numpy as np
import pandas as pd

from calculations.domain.services.route_mart_store import MartSidecarView
from calculations.domain.services.scenario_effects_compute import _COMPUTE_DTYPE
from scenarios.domain.repositories.elasticity import (
    ElasticityRulePointRepository,
    ElasticityRuleRepository,
)
from scenarios.domain.repositories.operational_elasticity import ModelRouteEconomicsRow
from scenarios.domain.services.operational_elasticity import build_model_route_group_indexes
from scenarios.domain.utils.elasticity_matching import (
    FloatPointsIndex,
    RuleIndex,
    apply_enterprise_load_cap,
    apply_enterprise_load_cap_float,
    build_float_points_index,
    build_points_index,
    build_rule_index,
    lookup_coefficient_for_marginality,
    lookup_coefficient_for_marginality_float,
    select_rule_for_keys_indexed,
    select_rule_for_route_indexed,
)
from scenarios.domain.utils.route_marginality import route_marginality_ratio_from_fields
from scenarios.models import ElasticityRule, Scenario

logger = logging.getLogger(__name__)

_SOURCE_CODE_TO_NAME = {
    0: "none",
    1: "direct_model",
    2: "holding_aggregate",
    3: "cargo_group_aggregate",
}


@dataclass
class FalloutComputeStats:
    routes_total: int = 0
    skip_elasticity: int = 0
    skip_no_volume: int = 0
    skip_no_initial: int = 0
    skip_source_none: int = 0
    static_eligible: int = 0
    dynamic_eligible: int = 0
    source_direct_model: int = 0
    source_holding_aggregate: int = 0
    source_cargo_group_aggregate: int = 0
    routes_computed: int = 0
    cells_computed: int = 0
    aggregate_calls: int = 0
    model_row_iters: int = 0
    model_routes_pool: int = 0
    holding_groups: int = 0
    cargo_groups: int = 0
    years_count: int = 0
    loop_routes: int = 0

    def to_timings(self) -> dict[str, int]:
        """Ключи для merge в timings (compact / compute-pandas meta)."""
        eligible_pct = 0
        if self.routes_total > 0:
            eligible_pct = int(self.dynamic_eligible * 10000 / self.routes_total)
        return {
            "fallout_routes_total": self.routes_total,
            "fallout_skip_elasticity": self.skip_elasticity,
            "fallout_skip_no_volume": self.skip_no_volume,
            "fallout_skip_no_initial": self.skip_no_initial,
            "fallout_skip_source_none": self.skip_source_none,
            "fallout_static_eligible": self.static_eligible,
            "fallout_dynamic_eligible": self.dynamic_eligible,
            "fallout_eligible_bps": eligible_pct,
            "fallout_source_direct": self.source_direct_model,
            "fallout_source_holding": self.source_holding_aggregate,
            "fallout_source_cargo_group": self.source_cargo_group_aggregate,
            "fallout_routes_computed": self.routes_computed,
            "fallout_cells_computed": self.cells_computed,
            "fallout_aggregate_calls": self.aggregate_calls,
            "fallout_model_row_iters": self.model_row_iters,
            "fallout_model_routes_pool": self.model_routes_pool,
            "fallout_holding_groups": self.holding_groups,
            "fallout_cargo_groups": self.cargo_groups,
            "fallout_years": self.years_count,
            "fallout_loop_routes": self.loop_routes,
        }


def _compute_eligibility_masks(
    *,
    skip: np.ndarray,
    source_codes: np.ndarray,
    volumes: np.ndarray,
    initial_charge: np.ndarray,
    n_routes: int,
) -> tuple[np.ndarray, np.ndarray, FalloutComputeStats]:
    initial = np.asarray(initial_charge[:n_routes], dtype=_COMPUTE_DTYPE)
    active = ~skip.astype(bool)
    has_volume = active & (volumes > 0)
    has_initial = has_volume & (initial > 0)
    has_source = has_initial & (source_codes != 0)
    static_ok = active & (volumes > 0) & (source_codes != 0)

    stats = FalloutComputeStats(
        routes_total=n_routes,
        skip_elasticity=int(skip.sum()),
        skip_no_volume=int((active & (volumes <= 0)).sum()),
        skip_no_initial=int((has_volume & (initial <= 0)).sum()),
        skip_source_none=int((has_initial & (source_codes == 0)).sum()),
        static_eligible=int(static_ok.sum()),
        dynamic_eligible=int(has_source.sum()),
        source_direct_model=int((has_source & (source_codes == 1)).sum()),
        source_holding_aggregate=int((has_source & (source_codes == 2)).sum()),
        source_cargo_group_aggregate=int((has_source & (source_codes == 3)).sum()),
    )
    return static_ok, has_source, stats


def log_fallout_diagnostics(stats: FalloutComputeStats) -> None:
    """Человекочитаемый лог профиля эластичности (INFO)."""
    total = stats.routes_total or 1
    eligible_pct = stats.dynamic_eligible * 100.0 / total
    computed_pct = stats.routes_computed * 100.0 / max(stats.dynamic_eligible, 1)
    avg_rows = 0.0
    if stats.aggregate_calls > 0:
        avg_rows = stats.model_row_iters / stats.aggregate_calls

    logger.info(
        "Elasticity fallout profile: total=%s loop_routes=%s eligible=%s (%.1f%%) "
        "computed_routes=%s (%.1f%% of eligible) | "
        "skip: elasticity=%s no_volume=%s no_initial=%s source_none=%s | "
        "source: direct=%s holding=%s cargo_group=%s | "
        "aggregate_calls=%s model_row_iters=%s avg_rows_per_call=%.1f | "
        "model_pool=%s holding_groups=%s cargo_groups=%s years=%s cells=%s",
        stats.routes_total,
        stats.loop_routes,
        stats.dynamic_eligible,
        eligible_pct,
        stats.routes_computed,
        computed_pct,
        stats.skip_elasticity,
        stats.skip_no_volume,
        stats.skip_no_initial,
        stats.skip_source_none,
        stats.source_direct_model,
        stats.source_holding_aggregate,
        stats.source_cargo_group_aggregate,
        stats.aggregate_calls,
        stats.model_row_iters,
        avg_rows,
        stats.model_routes_pool,
        stats.holding_groups,
        stats.cargo_groups,
        stats.years_count,
        stats.cells_computed,
    )


def _decimal_to_float(value: Decimal | float | int | None) -> float:
    if value is None:
        return 0.0
    return float(value)


def _optional_id(value: int | float) -> int | None:
    code = int(value)
    return code or None


@dataclass(frozen=True)
class _ModelGroupArrays:
    cargo_group_id: np.ndarray
    cargo_id: np.ndarray
    message_type_id: np.ndarray
    market: np.ndarray
    production: np.ndarray
    total: np.ndarray
    rzd: np.ndarray
    operators: np.ndarray
    transshipment: np.ndarray
    enterprise: np.ndarray
    weight: np.ndarray
    n: int

    @classmethod
    def from_rows(cls, rows: list[ModelRouteEconomicsRow]) -> _ModelGroupArrays:
        n = len(rows)
        if n == 0:
            return cls(
                cargo_group_id=np.empty(0, dtype=np.int32),
                cargo_id=np.empty(0, dtype=np.int32),
                message_type_id=np.empty(0, dtype=np.int32),
                market=np.empty(0, dtype=np.float64),
                production=np.empty(0, dtype=np.float64),
                total=np.empty(0, dtype=np.float64),
                rzd=np.empty(0, dtype=np.float64),
                operators=np.empty(0, dtype=np.float64),
                transshipment=np.empty(0, dtype=np.float64),
                enterprise=np.empty(0, dtype=np.float64),
                weight=np.empty(0, dtype=np.float64),
                n=0,
            )
        return cls(
            cargo_group_id=np.array(
                [row.cargo_group_id or 0 for row in rows],
                dtype=np.int32,
            ),
            cargo_id=np.array([row.cargo_id or 0 for row in rows], dtype=np.int32),
            message_type_id=np.array(
                [row.message_type_id or 0 for row in rows],
                dtype=np.int32,
            ),
            market=np.array(
                [_decimal_to_float(row.market_price_per_ton) for row in rows],
                dtype=np.float64,
            ),
            production=np.array(
                [_decimal_to_float(row.production_cost_per_ton) for row in rows],
                dtype=np.float64,
            ),
            total=np.array(
                [_decimal_to_float(row.total_cost_per_ton) for row in rows],
                dtype=np.float64,
            ),
            rzd=np.array(
                [_decimal_to_float(row.rzd_cost_total_per_ton) for row in rows],
                dtype=np.float64,
            ),
            operators=np.array(
                [_decimal_to_float(row.operators_cost_per_ton) for row in rows],
                dtype=np.float64,
            ),
            transshipment=np.array(
                [
                    _decimal_to_float(row.transshipment_cost_per_ton)
                    for row in rows
                ],
                dtype=np.float64,
            ),
            enterprise=np.array(
                [
                    _decimal_to_float(row.enterprise_load_coefficient)
                    for row in rows
                ],
                dtype=np.float64,
            ),
            weight=np.array(
                [_decimal_to_float(row.transport_volume_tons) for row in rows],
                dtype=np.float64,
            ),
            n=n,
        )


def _build_model_group_array_index(
    groups: dict[tuple, list[ModelRouteEconomicsRow]],
) -> dict[tuple, _ModelGroupArrays]:
    return {key: _ModelGroupArrays.from_rows(rows) for key, rows in groups.items()}


def _marginality_from_values(
    *,
    market: float,
    production: float,
    total: float,
    rzd: float,
    operators: float,
    transshipment: float,
    charge_ratio: float,
) -> float:
    return route_marginality_ratio_from_fields(
        market_price_per_ton=market,
        production_cost_per_ton=production,
        total_cost_per_ton=total,
        rzd_cost_total_per_ton=_scaled_rzd(rzd, charge_ratio),
        operators_cost_per_ton=operators,
        transshipment_cost_per_ton=transshipment,
    )


def _retention_coefficient_float(
    *,
    cargo_group_id: int | None,
    cargo_id: int | None,
    message_type_id: int | None,
    margin: float,
    base_margin: float | None,
    enterprise: float,
    scenario: Scenario,
    rule_index: RuleIndex,
    float_points_index: FloatPointsIndex,
) -> float | None:
    rule = select_rule_for_keys_indexed(
        rule_index,
        cargo_group_id=cargo_group_id,
        cargo_id=cargo_id,
        message_type_id=message_type_id,
    )
    if rule is None:
        return None

    current_coefficient = lookup_coefficient_for_marginality_float(
        rule.id,
        margin,
        float_points_index,
    )
    if current_coefficient is None:
        return None

    if scenario.retention_coefficient_mode == "relative_to_base":
        resolved_base_margin = (
            margin if base_margin is None else base_margin
        )
        base_coefficient = lookup_coefficient_for_marginality_float(
            rule.id,
            resolved_base_margin,
            float_points_index,
        )
        if base_coefficient is None:
            return None
        coefficient = 1.0 + current_coefficient - base_coefficient
    else:
        coefficient = current_coefficient

    return apply_enterprise_load_cap_float(
        coefficient,
        enterprise,
        enabled=bool(scenario.consider_enterprise_load),
    )


def _weighted_retention_numpy(
    group: _ModelGroupArrays,
    *,
    charge_ratio: float,
    scenario: Scenario,
    rule_index: RuleIndex,
    float_points_index: FloatPointsIndex,
) -> float | None:
    weighted = 0.0
    total_weight = 0.0
    for index in range(group.n):
        weight = float(group.weight[index])
        if weight <= 0.0:
            continue

        market = float(group.market[index])
        production = float(group.production[index])
        total = float(group.total[index])
        rzd = float(group.rzd[index])
        operators = float(group.operators[index])
        transshipment = float(group.transshipment[index])
        margin = _marginality_from_values(
            market=market,
            production=production,
            total=total,
            rzd=rzd,
            operators=operators,
            transshipment=transshipment,
            charge_ratio=charge_ratio,
        )
        base_margin = _marginality_from_values(
            market=market,
            production=production,
            total=total,
            rzd=rzd,
            operators=operators,
            transshipment=transshipment,
            charge_ratio=1.0,
        )
        coefficient = _retention_coefficient_float(
            cargo_group_id=_optional_id(group.cargo_group_id[index]),
            cargo_id=_optional_id(group.cargo_id[index]),
            message_type_id=_optional_id(group.message_type_id[index]),
            margin=margin,
            base_margin=base_margin,
            enterprise=float(group.enterprise[index]),
            scenario=scenario,
            rule_index=rule_index,
            float_points_index=float_points_index,
        )
        if coefficient is None:
            continue
        weighted += coefficient * weight
        total_weight += weight

    if total_weight <= 0.0:
        return None
    return weighted / total_weight


@dataclass
class _EconomicsProxy:
    cargo_id: int | None
    message_type_id: int | None
    market_price_per_ton: Decimal | None
    production_cost_per_ton: Decimal | None
    total_cost_per_ton: Decimal | None
    rzd_cost_total_per_ton: Decimal | None
    operators_cost_per_ton: Decimal | None
    transshipment_cost_per_ton: Decimal | None
    enterprise_load_coefficient: Decimal | None

    def __init__(
        self,
        *,
        cargo_id: int | None,
        cargo_group_id: int | None,
        message_type_id: int | None,
        market_price_per_ton: Decimal | None,
        production_cost_per_ton: Decimal | None,
        total_cost_per_ton: Decimal | None,
        rzd_cost_total_per_ton: Decimal | None,
        operators_cost_per_ton: Decimal | None,
        transshipment_cost_per_ton: Decimal | None,
        enterprise_load_coefficient: Decimal | None,
    ):
        self.cargo_id = cargo_id
        self.cargo_group_id = cargo_group_id
        self.message_type_id = message_type_id
        self.market_price_per_ton = market_price_per_ton
        self.production_cost_per_ton = production_cost_per_ton
        self.total_cost_per_ton = total_cost_per_ton
        self.rzd_cost_total_per_ton = rzd_cost_total_per_ton
        self.operators_cost_per_ton = operators_cost_per_ton
        self.transshipment_cost_per_ton = transshipment_cost_per_ton
        self.enterprise_load_coefficient = enterprise_load_coefficient

    @property
    def cargo(self):
        if self.cargo_id is None:
            return None
        return _CargoGroupProxy(self.cargo_group_id)


@dataclass
class _CargoGroupProxy:
    cargo_group_id: int | None


def _proxy_from_model_row(
    row: ModelRouteEconomicsRow,
    *,
    rzd: Decimal | None = None,
) -> _EconomicsProxy:
    return _EconomicsProxy(
        cargo_id=row.cargo_id,
        cargo_group_id=row.cargo_group_id,
        message_type_id=row.message_type_id,
        market_price_per_ton=row.market_price_per_ton,
        production_cost_per_ton=row.production_cost_per_ton,
        total_cost_per_ton=row.total_cost_per_ton,
        rzd_cost_total_per_ton=rzd if rzd is not None else row.rzd_cost_total_per_ton,
        operators_cost_per_ton=row.operators_cost_per_ton,
        transshipment_cost_per_ton=row.transshipment_cost_per_ton,
        enterprise_load_coefficient=row.enterprise_load_coefficient,
    )


def _scaled_rzd(base_rzd: float, charge_ratio: float) -> float:
    if base_rzd <= 0:
        return 0.0
    return base_rzd * charge_ratio


def _marginality_decimal(
    proxy: _EconomicsProxy,
    *,
    charge_ratio: float,
) -> Decimal:
    base_rzd = float(proxy.rzd_cost_total_per_ton or 0)
    scaled_rzd = _scaled_rzd(base_rzd, charge_ratio)
    ratio = route_marginality_ratio_from_fields(
        market_price_per_ton=float(proxy.market_price_per_ton or 0),
        production_cost_per_ton=float(proxy.production_cost_per_ton or 0),
        total_cost_per_ton=float(proxy.total_cost_per_ton or 0),
        rzd_cost_total_per_ton=scaled_rzd,
        operators_cost_per_ton=float(proxy.operators_cost_per_ton or 0),
        transshipment_cost_per_ton=float(proxy.transshipment_cost_per_ton or 0),
    )
    return Decimal(str(ratio))


def _retention_for_proxy(
    proxy: _EconomicsProxy,
    scenario: Scenario,
    marginality_ratio: Decimal,
    rules: list[ElasticityRule],  # legacy signature compatibility (kept for non-hot paths)
    *,
    rule_index,
    points_index,
    base_marginality_ratio: Decimal | None = None,
) -> Decimal | None:
    rule = select_rule_for_route_indexed(proxy, rule_index)  # type: ignore[arg-type]
    if rule is None:
        return None

    current_coefficient = lookup_coefficient_for_marginality(
        rule,
        marginality_ratio,
        points_index=points_index,
    )
    if current_coefficient is None:
        return None

    mode = scenario.retention_coefficient_mode
    if mode == "relative_to_base":
        base_marginality = base_marginality_ratio
        if base_marginality is None:
            base_marginality = _marginality_decimal(proxy, charge_ratio=1.0)
        base_coefficient = lookup_coefficient_for_marginality(
            rule,
            base_marginality,
            points_index=points_index,
        )
        if base_coefficient is None:
            return None
        coefficient = Decimal("1") + current_coefficient - base_coefficient
    else:
        coefficient = current_coefficient

    return apply_enterprise_load_cap(
        coefficient,
        proxy.enterprise_load_coefficient,
        enabled=bool(scenario.consider_enterprise_load),
    )


def _weighted_retention(
    model_rows: list[ModelRouteEconomicsRow],
    scenario: Scenario,
    rules: list[ElasticityRule],
    *,
    charge_ratio: float,
    rule_index,
    points_index,
) -> Decimal | None:
    weighted = Decimal("0")
    total_weight = Decimal("0")
    for row in model_rows:
        base_rzd = float(row.rzd_cost_total_per_ton or 0)
        proxy = _proxy_from_model_row(
            row,
            rzd=Decimal(str(base_rzd)),
        )
        margin = _marginality_decimal(proxy, charge_ratio=charge_ratio)
        base_margin = _marginality_decimal(proxy, charge_ratio=1.0)
        k = _retention_for_proxy(
            proxy,
            scenario,
            margin,
            rules,
            rule_index=rule_index,
            points_index=points_index,
            base_marginality_ratio=base_margin,
        )
        if k is None:
            continue
        weight = row.transport_volume_tons
        if weight is None or weight <= 0:
            continue
        weighted += k * weight
        total_weight += weight
    if total_weight <= 0:
        return None
    return weighted / total_weight


def _label_at(labels: list[str], code: int) -> str:
    if code < 0 or code >= len(labels):
        return "—"
    return labels[code]


def compute_fallout_arrays(
    sidecar: MartSidecarView | pd.DataFrame,
    *,
    scenario: Scenario,
    years: list[int],
    initial_charge: np.ndarray,
    charge_by_year: np.ndarray,
    turnover_coef: np.ndarray,
    model_rows: list[ModelRouteEconomicsRow],
    dimension_labels: dict[str, list[str]] | None = None,
) -> tuple[np.ndarray, np.ndarray, FalloutComputeStats]:
    n_routes = len(sidecar)
    n_years = len(years)
    volume_fallout = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    money_fallout = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    empty_stats = FalloutComputeStats(routes_total=n_routes, years_count=n_years)

    if not scenario.consider_demand_elasticity or not scenario.elasticity_set_id:
        return volume_fallout, money_fallout, empty_stats

    rules = ElasticityRuleRepository().list_by_set(scenario.elasticity_set_id)
    if not rules:
        return volume_fallout, money_fallout, empty_stats

    rule_index = build_rule_index(rules)
    point_repo = ElasticityRulePointRepository()
    points_by_rule = point_repo.list_by_rules([rule.id for rule in rules])
    points_index = build_points_index(points_by_rule)
    float_points_index = build_float_points_index(points_index)
    holding_groups, cargo_groups = build_model_route_group_indexes(model_rows)
    holding_arrays = _build_model_group_array_index(holding_groups)
    cargo_arrays = _build_model_group_array_index(cargo_groups)
    labels = dimension_labels or {}

    def _col(name: str) -> np.ndarray:
        if isinstance(sidecar, MartSidecarView):
            if name not in sidecar.column_names:
                return np.zeros(n_routes, dtype=_COMPUTE_DTYPE)
            return np.asarray(sidecar[name], dtype=_COMPUTE_DTYPE)
        if name not in sidecar.columns:
            return np.zeros(n_routes, dtype=_COMPUTE_DTYPE)
        # DataFrame path: некоторые колонки могут быть строками после Postgres COPY.
        if name == "skip_elasticity":
            raw = sidecar[name]
            if pd.api.types.is_bool_dtype(raw):
                values = raw.fillna(True)
                return values.to_numpy(dtype=np.uint8, copy=False)
            if pd.api.types.is_numeric_dtype(raw):
                values = pd.to_numeric(raw, errors="coerce").fillna(1).astype(int) != 0
                return values.to_numpy(dtype=np.uint8, copy=False)
            s = raw.fillna("t").astype(str).str.strip().str.lower()
            values = s.isin({"1", "true", "t", "yes", "y", "on"})
            return values.to_numpy(dtype=np.uint8, copy=False)
        if name == "elasticity_source":
            raw = sidecar[name].fillna("none").astype(str)
            codes = raw.map(
                {
                    "none": 0,
                    "direct_model": 1,
                    "holding_aggregate": 2,
                    "cargo_group_aggregate": 3,
                },
            ).fillna(0)
            return codes.to_numpy(dtype=np.uint8, copy=False)
        return sidecar[name].to_numpy(dtype=_COMPUTE_DTYPE, copy=False)

    skip = _col("skip_elasticity").astype(bool)
    source_codes = _col("elasticity_source").astype(np.uint8)
    volumes = _col("transport_volume_tons")
    if not np.any(volumes):
        volumes = _col("transport_volume_tons")
    message_type_id = _col("message_type_id")
    cargo_group_id = _col("cargo_group_id")

    dim_holding = _col("dim_holding").astype(np.int32)
    dim_direction = _col("dim_direction").astype(np.int32)
    holding_labels = labels.get("holding", [])
    direction_labels = labels.get("direction", [])

    mr_market = _col("mr_market_price_per_ton")
    mr_prod = _col("mr_production_cost_per_ton")
    mr_total = _col("mr_total_cost_per_ton")
    mr_rzd = _col("mr_rzd_cost_total_per_ton")
    mr_oper = _col("mr_operators_cost_per_ton")
    mr_per = _col("mr_transshipment_cost_per_ton")
    mr_enterprise = _col("mr_enterprise_load_coefficient")
    mr_cargo_id = _col("mr_cargo_id")
    mr_message_type_id = _col("mr_message_type_id")
    mr_cargo_group_id = _col("mr_cargo_group_id")

    _static_ok, eligible_mask, stats = _compute_eligibility_masks(
        skip=skip,
        source_codes=source_codes,
        volumes=volumes,
        initial_charge=initial_charge,
        n_routes=n_routes,
    )
    stats.model_routes_pool = len(model_rows)
    stats.holding_groups = len(holding_groups)
    stats.cargo_groups = len(cargo_groups)
    stats.years_count = n_years
    eligible_indices = np.flatnonzero(eligible_mask)
    stats.loop_routes = int(eligible_indices.size)

    def _weighted_retention_counted(
        group: _ModelGroupArrays,
        *,
        charge_ratio: float,
    ) -> float | None:
        stats.aggregate_calls += 1
        stats.model_row_iters += group.n
        return _weighted_retention_numpy(
            group,
            charge_ratio=charge_ratio,
            scenario=scenario,
            rule_index=rule_index,
            float_points_index=float_points_index,
        )

    for route_index in eligible_indices:
        route_index = int(route_index)
        volume = float(volumes[route_index])
        initial = float(initial_charge[route_index])
        source = _SOURCE_CODE_TO_NAME[int(source_codes[route_index])]

        route_had_fallout = False
        for year_index, _year in enumerate(years):
            turnover = float(turnover_coef[route_index, year_index])
            if year_index == 0:
                continue

            current_charge = float(charge_by_year[route_index, year_index])
            current_tariff = current_charge / turnover if turnover else initial
            charge_ratio = current_tariff / initial if initial > 0 else 1.0
            prev_charge = current_charge

            k: float | None = None
            aggregate_group: _ModelGroupArrays | None = None

            if source == "direct_model":
                direct_message_type_id = _optional_id(
                    int(message_type_id[route_index])
                    or int(mr_message_type_id[route_index]),
                )
                direct_cargo_group_id = _optional_id(
                    int(cargo_group_id[route_index])
                    or int(mr_cargo_group_id[route_index]),
                )
                direct_cargo_id = _optional_id(int(mr_cargo_id[route_index]))
                market = float(mr_market[route_index])
                production = float(mr_prod[route_index])
                total = float(mr_total[route_index])
                rzd = float(mr_rzd[route_index])
                operators = float(mr_oper[route_index])
                transshipment = float(mr_per[route_index])
                margin = _marginality_from_values(
                    market=market,
                    production=production,
                    total=total,
                    rzd=rzd,
                    operators=operators,
                    transshipment=transshipment,
                    charge_ratio=charge_ratio,
                )
                base_margin = _marginality_from_values(
                    market=market,
                    production=production,
                    total=total,
                    rzd=rzd,
                    operators=operators,
                    transshipment=transshipment,
                    charge_ratio=1.0,
                )
                k = _retention_coefficient_float(
                    cargo_group_id=direct_cargo_group_id,
                    cargo_id=direct_cargo_id,
                    message_type_id=direct_message_type_id,
                    margin=margin,
                    base_margin=base_margin,
                    enterprise=float(mr_enterprise[route_index]),
                    scenario=scenario,
                    rule_index=rule_index,
                    float_points_index=float_points_index,
                )
            elif source == "holding_aggregate":
                key = (
                    _label_at(holding_labels, int(dim_holding[route_index])),
                    _label_at(direction_labels, int(dim_direction[route_index])),
                    int(message_type_id[route_index]) or None,
                    int(cargo_group_id[route_index]) or None,
                )
                aggregate_group = holding_arrays.get(key)
                if aggregate_group is not None and aggregate_group.n > 0:
                    k = _weighted_retention_counted(
                        aggregate_group,
                        charge_ratio=charge_ratio,
                    )
            elif source == "cargo_group_aggregate":
                key = (
                    int(cargo_group_id[route_index]) or None,
                    _label_at(direction_labels, int(dim_direction[route_index])),
                    int(message_type_id[route_index]) or None,
                )
                aggregate_group = cargo_arrays.get(key)
                if aggregate_group is not None and aggregate_group.n > 0:
                    k = _weighted_retention_counted(
                        aggregate_group,
                        charge_ratio=charge_ratio,
                    )
            else:
                k = None

            if k is None:
                continue

            k_float = k
            volume_fallout[route_index, year_index] = round(
                volume * turnover * (k_float - 1.0),
                4,
            )
            money_fallout[route_index, year_index] = round(
                prev_charge * (k_float - 1.0),
                2,
            )
            stats.cells_computed += 1
            route_had_fallout = True

        if route_had_fallout:
            stats.routes_computed += 1

    log_fallout_diagnostics(stats)
    return volume_fallout, money_fallout, stats
