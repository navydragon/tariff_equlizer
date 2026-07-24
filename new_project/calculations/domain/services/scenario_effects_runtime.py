from __future__ import annotations

import threading
from collections import OrderedDict
from pathlib import Path

import pandas as pd

from calculations.domain.services.route_mask_cache import mask_cache_dir
from calculations.domain.services.route_mart_store import (
    MartMeta,
    ensure_compute_sidecars,
    load_mart_meta,
    load_mart_sidecar,
    load_route_mart_parquet,
    resolve_mart_parquet_path,
)
from calculations.domain.services.scenario_effects_cache import CompactRouteEffects
from calculations.domain.services.scenario_effects_compact import (
    build_compact_from_arrays,
    prepare_compact_inputs,
)
from calculations.domain.services.scenario_effects_compute import (
    compute_arrays_full,
    rule_specs_from_context,
)
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario

_RUNTIME_CACHE_MAX_ENTRIES = 3
_runtime_cache_guard = threading.Lock()
_runtime_cache: OrderedDict[tuple[int, str, bool], CompactRouteEffects] = OrderedDict()


def clear_runtime_compact_cache() -> None:
    with _runtime_cache_guard:
        _runtime_cache.clear()


def get_or_compute_compact(
    *,
    scenario: Scenario,
    data_version: str,
    include_rule_by_year: bool,
) -> CompactRouteEffects:
    key = (scenario.id, data_version, include_rule_by_year)
    with _runtime_cache_guard:
        cached = _runtime_cache.get(key)
        if cached is not None:
            _runtime_cache.move_to_end(key)
            return cached

    compact = _compute_compact_on_demand(
        scenario=scenario,
        include_rule_by_year=include_rule_by_year,
    )

    with _runtime_cache_guard:
        _runtime_cache[key] = compact
        _runtime_cache.move_to_end(key)
        while len(_runtime_cache) > _RUNTIME_CACHE_MAX_ENTRIES:
            _runtime_cache.popitem(last=False)

    return compact


def _resolve_parquet_path(scenario: Scenario) -> Path:
    parquet_path = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
    if not parquet_path.is_file():
        raise ValueError(f"Route mart parquet missing for route_set_id={scenario.route_set_id}")
    if not ensure_compute_sidecars(parquet_path):
        raise ValueError(f"Route mart sidecars incomplete for {parquet_path}")
    return parquet_path


def _load_compact_dataframe(
    parquet_path: Path,
    *,
    mart_meta: MartMeta | None,
) -> pd.DataFrame:
    volume_sidecar, _volume_timings = load_mart_sidecar(
        parquet_path,
        include_charge=False,
        include_volume=True,
    )
    if volume_sidecar.empty or "transport_volume_tons" not in volume_sidecar:
        compact_df = load_route_mart_parquet(
            parquet_path,
            columns=["transport_volume_tons"],
        )
        dims_sidecar, _ = load_mart_sidecar(
            parquet_path,
            include_charge=False,
        )
        if not dims_sidecar.empty:
            for column in dims_sidecar.column_names:
                compact_df[column] = dims_sidecar[column]
    else:
        compact_df = volume_sidecar.to_dataframe()
        dims_sidecar, _ = load_mart_sidecar(
            parquet_path,
            include_charge=False,
        )
        if not dims_sidecar.empty:
            for column in dims_sidecar.column_names:
                if column not in compact_df.columns:
                    compact_df[column] = dims_sidecar[column]

    return compact_df


def _compute_compact_on_demand(
    *,
    scenario: Scenario,
    include_rule_by_year: bool,
) -> CompactRouteEffects:
    parquet_path = _resolve_parquet_path(scenario)
    sidecar, _sidecar_timings = load_mart_sidecar(
        parquet_path,
        include_charge=True,
    )
    if sidecar.empty or "freight_charge_rub" not in sidecar:
        raise ValueError(f"Charge sidecar missing for {parquet_path}")

    mart_meta = load_mart_meta(parquet_path)
    tariff_load = TariffLoadService()
    context = tariff_load.build_scenario_context(scenario)
    years = context.years
    rule_specs = rule_specs_from_context(tariff_load, context)

    _global_totals, _timings, arrays = compute_arrays_full(
        sidecar,
        years=years,
        base_coef_by_year=context.base_coef_by_year,
        rule_specs=rule_specs,
        route_set_id=scenario.route_set_id,
        mart_meta=mart_meta,
        mask_cache_dir=mask_cache_dir(route_set_id=scenario.route_set_id),
        include_rule_by_year=include_rule_by_year,
    )
    if arrays is None:
        raise ValueError("compute_arrays_full returned no arrays")

    compact_df = _load_compact_dataframe(parquet_path, mart_meta=mart_meta)
    dimensions, dimension_labels, volume = prepare_compact_inputs(
        compact_df,
        mart_meta,
    )
    return build_compact_from_arrays(
        years=years,
        initial=arrays.initial,
        base_by_year=arrays.base_by_year,
        rules_by_year_arr=arrays.rules_by_year_arr,
        charge_by_year=arrays.charge_by_year,
        rule_meta=arrays.rule_meta,
        rule_by_year=arrays.rule_by_year,
        dimensions=dimensions,
        dimension_labels=dimension_labels,
        volume=volume,
    )
