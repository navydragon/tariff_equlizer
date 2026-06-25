from __future__ import annotations

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
    apply_enterprise_load_cap,
    build_points_index,
    build_rule_index,
    lookup_coefficient_for_marginality,
    select_rule_for_route_indexed,
)
from scenarios.domain.utils.route_marginality import route_marginality_ratio_from_fields
from scenarios.models import ElasticityRule, Scenario

_SOURCE_CODE_TO_NAME = {
    0: "none",
    1: "direct_model",
    2: "holding_aggregate",
    3: "cargo_group_aggregate",
}


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
) -> tuple[np.ndarray, np.ndarray]:
    n_routes = len(sidecar)
    n_years = len(years)
    volume_fallout = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    money_fallout = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)

    if not scenario.consider_demand_elasticity or not scenario.elasticity_set_id:
        return volume_fallout, money_fallout

    rules = ElasticityRuleRepository().list_by_set(scenario.elasticity_set_id)
    if not rules:
        return volume_fallout, money_fallout

    rule_index = build_rule_index(rules)
    point_repo = ElasticityRulePointRepository()
    points_by_rule = point_repo.list_by_rules([rule.id for rule in rules])
    points_index = build_points_index(points_by_rule)
    holding_groups, cargo_groups = build_model_route_group_indexes(model_rows)
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

    for route_index in range(n_routes):
        if skip[route_index]:
            continue

        volume = float(volumes[route_index])
        if volume <= 0:
            continue

        initial = float(initial_charge[route_index])
        if initial <= 0:
            continue

        source = _SOURCE_CODE_TO_NAME.get(
            int(source_codes[route_index]),
            "none",
        )
        if source == "none":
            continue

        for year_index, _year in enumerate(years):
            turnover = float(turnover_coef[route_index, year_index])
            if year_index == 0:
                continue

            current_charge = float(charge_by_year[route_index, year_index])
            current_tariff = current_charge / turnover if turnover else initial
            charge_ratio = current_tariff / initial if initial > 0 else 1.0
            prev_charge = current_charge

            proxy: _EconomicsProxy | None = None
            aggregate_rows: list[ModelRouteEconomicsRow] | None = None

            if source == "direct_model":
                # Для operational маршрутов источник экономики — модельный маршрут,
                # но матчинговые поля (message_type/cargo_group) должны соответствовать
                # самому operational маршруту, иначе правило эластичности выбирается неверно.
                mt = int(message_type_id[route_index]) or int(mr_message_type_id[route_index]) or None
                cg = int(cargo_group_id[route_index]) or int(mr_cargo_group_id[route_index]) or None
                proxy = _EconomicsProxy(
                    cargo_id=int(mr_cargo_id[route_index]) or None,
                    cargo_group_id=cg,
                    message_type_id=mt,
                    market_price_per_ton=Decimal(str(mr_market[route_index])),
                    production_cost_per_ton=Decimal(str(mr_prod[route_index])),
                    total_cost_per_ton=Decimal(str(mr_total[route_index])),
                    rzd_cost_total_per_ton=Decimal(str(mr_rzd[route_index])),
                    operators_cost_per_ton=Decimal(str(mr_oper[route_index])),
                    transshipment_cost_per_ton=Decimal(str(mr_per[route_index])),
                    enterprise_load_coefficient=Decimal(str(mr_enterprise[route_index])),
                )
            elif source == "holding_aggregate":
                key = (
                    _label_at(holding_labels, int(dim_holding[route_index])),
                    _label_at(direction_labels, int(dim_direction[route_index])),
                    int(message_type_id[route_index]) or None,
                    int(cargo_group_id[route_index]) or None,
                )
                aggregate_rows = holding_groups.get(key, [])
            elif source == "cargo_group_aggregate":
                key = (
                    int(cargo_group_id[route_index]) or None,
                    _label_at(direction_labels, int(dim_direction[route_index])),
                    int(message_type_id[route_index]) or None,
                )
                aggregate_rows = cargo_groups.get(key, [])

            if proxy is not None:
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
            elif aggregate_rows:
                k = _weighted_retention(
                    aggregate_rows,
                    scenario,
                    rules,
                    charge_ratio=charge_ratio,
                    rule_index=rule_index,
                    points_index=points_index,
                )
            else:
                k = None

            if k is None:
                continue

            k_float = float(k)
            volume_fallout[route_index, year_index] = round(
                volume * turnover * (k_float - 1.0),
                4,
            )
            money_fallout[route_index, year_index] = round(
                prev_charge * (k_float - 1.0),
                2,
            )

    return volume_fallout, money_fallout
