from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from pathlib import Path

import numpy as np
import pandas as pd

from concurrent.futures import ThreadPoolExecutor

from calculations.domain.services.route_mask_cache import build_or_load_rule_mask
from calculations.domain.services.route_mart_store import MartMeta, MartSidecarView
from calculations.domain.services.scenario_effects_compact import _COMPUTE_DTYPE
from calculations.domain.services.scenario_effects_cache import EarlyGroupSnapshot
from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from calculations.domain.services.tariff_load import ScenarioTariffContext, TariffLoadService
from scenarios.models import Scenario
from core.domain.route.turnover_coefficients import TURNOVER_COEF_YEARS


def effective_rule_coefficient(coefficient: float, base_percent: float) -> float:
    return 1.0 + (coefficient - 1.0) * base_percent / 100.0


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


@dataclass(frozen=True)
class RuleComputeSpec:
    id: int
    name: str
    base_percent: float
    conditions: list[dict]
    year_values: dict[int, float]


@dataclass
class FullComputeArrays:
    initial: np.ndarray
    base_by_year: np.ndarray
    rules_by_year_arr: np.ndarray
    charge_by_year: np.ndarray
    rule_meta: list[tuple[int, str]]
    rule_by_year: np.ndarray | None
    turnover_coef: np.ndarray | None = None
    volume_fallout_by_year: np.ndarray | None = None
    money_fallout_by_year: np.ndarray | None = None


def rule_specs_from_context(
    tariff_load: TariffLoadService,
    context: ScenarioTariffContext,
) -> list[RuleComputeSpec]:
    specs: list[RuleComputeSpec] = []
    for rule in context.rules:
        specs.append(
            RuleComputeSpec(
                id=rule.id,
                name=rule.name,
                base_percent=float(rule.base_percent),
                conditions=tariff_load._rule_conditions_payload(rule),
                year_values={
                    value.year: float(value.coefficient)
                    for value in rule.year_values.all()
                },
            ),
        )
    return specs


def _base_coef_array(
    years: list[int],
    base_coef_by_year: dict[int, Decimal],
) -> np.ndarray:
    return np.array(
        [float(base_coef_by_year.get(year, Decimal("1"))) for year in years],
        dtype=_COMPUTE_DTYPE,
    )


def _sidecar_charge_array(sidecar: MartSidecarView | pd.DataFrame) -> np.ndarray:
    if isinstance(sidecar, MartSidecarView):
        return np.asarray(sidecar["freight_charge_rub"], dtype=_COMPUTE_DTYPE)
    return sidecar["freight_charge_rub"].to_numpy(dtype=_COMPUTE_DTYPE, copy=False)


def _sidecar_volume_array(sidecar: MartSidecarView | pd.DataFrame) -> np.ndarray:
    if isinstance(sidecar, MartSidecarView):
        if "transport_volume_tons" not in sidecar.column_names:
            return np.zeros(len(sidecar), dtype=_COMPUTE_DTYPE)
        return np.asarray(sidecar["transport_volume_tons"], dtype=_COMPUTE_DTYPE)
    if "transport_volume_tons" not in sidecar.columns:
        return np.zeros(len(sidecar), dtype=_COMPUTE_DTYPE)
    return (
        pd.to_numeric(sidecar["transport_volume_tons"], errors="coerce")
        .fillna(0)
        .to_numpy(dtype=_COMPUTE_DTYPE, copy=False)
    )


def _resolve_group_codes_and_labels(
    sidecar: MartSidecarView | pd.DataFrame,
    group_dim: str,
    mart_meta: MartMeta | None,
) -> tuple[np.ndarray, list[str]] | None:
    dim_column = f"dim_{group_dim}"
    if isinstance(sidecar, MartSidecarView):
        if dim_column in sidecar.column_names:
            codes = np.asarray(sidecar[dim_column], dtype=np.int32)
            labels = (
                list(mart_meta.dimension_labels.get(group_dim, []))
                if mart_meta is not None and mart_meta.dimension_labels
                else []
            )
            if not labels:
                labels = [str(code) for code in range(int(codes.max()) + 1)]
            return codes, labels
        if group_dim not in sidecar.column_names:
            return None
        series = pd.Series(sidecar[group_dim]).astype(str)
    else:
        if dim_column in sidecar.columns:
            codes = sidecar[dim_column].to_numpy(dtype=np.int32, copy=False)
            labels = (
                list(mart_meta.dimension_labels.get(group_dim, []))
                if mart_meta is not None and mart_meta.dimension_labels
                else []
            )
            if not labels:
                labels = [str(code) for code in range(int(codes.max()) + 1)]
            return codes, labels
        if group_dim not in sidecar.columns:
            return None
        series = sidecar[group_dim].astype(str)

    codes, uniques = pd.factorize(series, sort=False)
    return codes.astype(np.int32, copy=False), uniques.tolist()


def _bincount_by_group(
    group_codes: np.ndarray,
    weights: np.ndarray,
    *,
    n_groups: int,
) -> np.ndarray:
    return np.bincount(
        group_codes,
        weights=weights,
        minlength=n_groups,
    ).astype(np.float64, copy=False)


def _stored_turnover_coef_matrix(
    sidecar: MartSidecarView | pd.DataFrame,
    *,
    n_routes: int,
) -> np.ndarray:
    if isinstance(sidecar, MartSidecarView):
        raw = sidecar.get("turnover_coef")
    elif "turnover_coef" in sidecar.columns:
        values = sidecar["turnover_coef"]
        if isinstance(values, pd.DataFrame):
            raw = values.to_numpy(dtype=_COMPUTE_DTYPE, copy=False)
        else:
            raw = np.asarray(values, dtype=_COMPUTE_DTYPE)
    else:
        raw = None
    if raw is None:
        return np.ones((n_routes, len(TURNOVER_COEF_YEARS)), dtype=_COMPUTE_DTYPE)
    matrix = np.asarray(raw, dtype=_COMPUTE_DTYPE)
    if matrix.ndim == 1:
        matrix = matrix.reshape(n_routes, len(TURNOVER_COEF_YEARS))
    return matrix


def build_turnover_coef_matrix(
    sidecar: MartSidecarView | pd.DataFrame,
    years: list[int],
    *,
    enabled: bool,
) -> np.ndarray:
    n_routes = len(sidecar)
    n_years = len(years)
    if not enabled or n_routes == 0 or n_years == 0:
        return np.ones((n_routes, n_years), dtype=_COMPUTE_DTYPE)

    stored = _stored_turnover_coef_matrix(sidecar, n_routes=n_routes)
    year_to_index = {year: index for index, year in enumerate(TURNOVER_COEF_YEARS)}
    result = np.ones((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    for year_index, year in enumerate(years):
        stored_index = year_to_index.get(year)
        if stored_index is not None:
            result[:, year_index] = stored[:, stored_index]
    return result


def _prepare_rules_state(
    sidecar: MartSidecarView | pd.DataFrame,
    *,
    years: list[int],
    rule_specs: list[RuleComputeSpec],
    route_set_id: int,
    mart_meta: MartMeta | None,
    mask_cache_dir: Path | None = None,
) -> tuple[
    np.ndarray,
    list[tuple[int, str]],
    list[np.ndarray],
    list[np.ndarray],
    dict[str, int],
]:
    n_routes = len(sidecar)
    n_years = len(years)
    rules_coef = np.ones((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    rule_meta: list[tuple[int, str]] = []
    rule_masks: list[np.ndarray] = []
    rule_effective_by_year: list[np.ndarray] = []

    import time

    t_masks = time.perf_counter()
    resolved_mask_dir = mask_cache_dir
    if resolved_mask_dir is None:
        from calculations.domain.services.route_mask_cache import mask_cache_dir as resolve_mask_cache_dir

        resolved_mask_dir = resolve_mask_cache_dir(route_set_id=route_set_id)

    def _build_mask(rule_spec: RuleComputeSpec) -> tuple[RuleComputeSpec, np.ndarray]:
        mask = build_or_load_rule_mask(
            route_set_id=route_set_id,
            rule_id=rule_spec.id,
            conditions=rule_spec.conditions,
            df=sidecar,
            mart_meta=mart_meta,
            cache_dir=resolved_mask_dir,
        )
        return rule_spec, mask

    max_workers = min(8, len(rule_specs) or 1)
    with ThreadPoolExecutor(max_workers=max_workers) as executor:
        mask_results = list(executor.map(_build_mask, rule_specs))

    for rule_spec, mask in mask_results:
        if not mask.any():
            continue

        effective_arr = np.array(
            [
                effective_rule_coefficient(
                    rule_spec.year_values.get(year, 1.0),
                    rule_spec.base_percent,
                )
                for year in years
            ],
            dtype=_COMPUTE_DTYPE,
        )
        rule_meta.append((rule_spec.id, rule_spec.name))
        rule_masks.append(mask)
        rule_effective_by_year.append(effective_arr)

        for year_index, _year in enumerate(years):
            rules_coef[mask, year_index] *= effective_arr[year_index]

    timings = {"masks_ms": int((time.perf_counter() - t_masks) * 1000)}
    return rules_coef, rule_meta, rule_masks, rule_effective_by_year, timings


def compute_kpi_totals(
    sidecar: MartSidecarView | pd.DataFrame,
    *,
    years: list[int],
    base_coef_by_year: dict[int, Decimal],
    rule_specs: list[RuleComputeSpec],
    route_set_id: int,
    mart_meta: MartMeta | None,
    consider_turnover_changes: bool = False,
    early_group_dim: str | None = None,
) -> tuple[GlobalTotals, EarlyGroupSnapshot | None, dict[str, int]]:
    import time

    timings: dict[str, int] = {}
    if isinstance(sidecar, MartSidecarView):
        if sidecar.empty:
            return GlobalTotals(), None, timings
    elif sidecar.empty:
        return GlobalTotals(), None, timings

    initial = _sidecar_charge_array(sidecar)
    volume = _sidecar_volume_array(sidecar)
    turnover_coef = build_turnover_coef_matrix(
        sidecar,
        years,
        enabled=consider_turnover_changes,
    )
    base_coef_arr = _base_coef_array(years, base_coef_by_year)

    rules_coef, rule_meta, _rule_masks, _rule_effective, mask_timings = (
        _prepare_rules_state(
            sidecar,
            years=years,
            rule_specs=rule_specs,
            route_set_id=route_set_id,
            mart_meta=mart_meta,
        )
    )
    timings.update(mask_timings)
    has_rules = bool(rule_meta)

    group_codes: np.ndarray | None = None
    group_labels: list[str] = []
    n_groups = 0
    charge_group_sums: dict[int, list[Decimal]] | None = None
    volume_group_sums: dict[int, list[Decimal]] | None = None
    if early_group_dim:
        resolved = _resolve_group_codes_and_labels(
            sidecar,
            early_group_dim,
            mart_meta,
        )
        if resolved is not None:
            group_codes, group_labels = resolved
            n_groups = len(group_labels)
            charge_group_sums = {year: [] for year in years}
            volume_group_sums = {year: [] for year in years}

    global_totals = GlobalTotals()
    baseline = initial * turnover_coef[:, 0]
    global_totals.baseline_total = _to_decimal(float(baseline.sum(dtype=np.float64)))
    global_totals.charge_by_year[years[0]] = global_totals.baseline_total

    tariff_prev = initial.copy()
    t_years = time.perf_counter()
    for year_index, year in enumerate(years):
        turnover_column = turnover_coef[:, year_index]
        if year_index == 0:
            charge_per_route = np.round(initial * turnover_column, 2)
            if charge_group_sums is not None and group_codes is not None:
                charge_group_sums[year] = [
                    _to_decimal(value)
                    for value in _bincount_by_group(
                        group_codes,
                        charge_per_route,
                        n_groups=n_groups,
                    )
                ]
                volume_per_route = np.round(volume * turnover_column, 2)
                volume_group_sums[year] = [
                    _to_decimal(value)
                    for value in _bincount_by_group(
                        group_codes,
                        volume_per_route,
                        n_groups=n_groups,
                    )
                ]
            continue

        base_coef = base_coef_arr[year_index]
        if not has_rules:
            tariff_current = np.round(tariff_prev * base_coef, 2)
            base_inc = np.round(tariff_prev * (base_coef - 1.0) * turnover_column, 2)
            rules_inc_sum = 0.0
        else:
            rules_column = rules_coef[:, year_index]
            tariff_current = np.round(
                tariff_prev * (base_coef + rules_column - 1.0),
                2,
            )
            base_inc = np.round(tariff_prev * (base_coef - 1.0) * turnover_column, 2)
            rules_inc_sum = float(
                np.round(tariff_prev * (rules_column - 1.0) * turnover_column, 2).sum(
                    dtype=np.float64,
                ),
            )

        current = np.round(tariff_current * turnover_column, 2)
        global_totals.charge_by_year[year] = _to_decimal(
            float(current.sum(dtype=np.float64)),
        )
        global_totals.base_by_year[year] = _to_decimal(float(base_inc.sum(dtype=np.float64)))
        if has_rules:
            global_totals.rules_by_year[year] = _to_decimal(rules_inc_sum)

        if charge_group_sums is not None and group_codes is not None:
            charge_group_sums[year] = [
                _to_decimal(value)
                for value in _bincount_by_group(
                    group_codes,
                    current,
                    n_groups=n_groups,
                )
            ]
            volume_per_route = np.round(volume * turnover_column, 2)
            volume_group_sums[year] = [
                _to_decimal(value)
                for value in _bincount_by_group(
                    group_codes,
                    volume_per_route,
                    n_groups=n_groups,
                )
            ]

        tariff_prev = tariff_current

    timings["years_loop_ms"] = int((time.perf_counter() - t_years) * 1000)
    timings["rule_by_year_ms"] = 0
    timings["totals_ms"] = 0

    early_snapshot: EarlyGroupSnapshot | None = None
    if (
        early_group_dim
        and charge_group_sums is not None
        and volume_group_sums is not None
        and group_labels
    ):
        early_snapshot = EarlyGroupSnapshot(
            group_dim=early_group_dim,
            dimension_labels=group_labels,
            charge_by_year=charge_group_sums,
            volume_by_year=volume_group_sums,
        )

    return global_totals, early_snapshot, timings


def compute_arrays_full(
    sidecar: MartSidecarView | pd.DataFrame,
    *,
    years: list[int],
    base_coef_by_year: dict[int, Decimal],
    rule_specs: list[RuleComputeSpec],
    route_set_id: int,
    mart_meta: MartMeta | None,
    mask_cache_dir: Path | None = None,
    include_rule_by_year: bool = True,
    consider_turnover_changes: bool = False,
    scenario: Scenario | None = None,
    model_rows: list | None = None,
    dimension_labels: dict[str, list[str]] | None = None,
) -> tuple[GlobalTotals, dict[str, int], FullComputeArrays | None]:
    import time

    timings: dict[str, int] = {}
    if isinstance(sidecar, MartSidecarView):
        if sidecar.empty:
            return GlobalTotals(), timings, None
    elif sidecar.empty:
        return GlobalTotals(), timings, None

    n_routes = len(sidecar)
    n_years = len(years)
    initial = _sidecar_charge_array(sidecar)
    turnover_coef = build_turnover_coef_matrix(
        sidecar,
        years,
        enabled=consider_turnover_changes,
    )
    base_coef_arr = _base_coef_array(years, base_coef_by_year)

    rules_coef, rule_meta, rule_masks, rule_effective_by_year, mask_timings = (
        _prepare_rules_state(
            sidecar,
            years=years,
            rule_specs=rule_specs,
            route_set_id=route_set_id,
            mart_meta=mart_meta,
            mask_cache_dir=mask_cache_dir,
        )
    )
    timings.update(mask_timings)

    has_rules = bool(rule_meta)
    n_rules = len(rule_meta)
    rule_by_year_arr = (
        np.zeros((n_rules, n_routes, n_years), dtype=_COMPUTE_DTYPE)
        if n_rules and include_rule_by_year
        else None
    )

    charge_by_year = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    base_by_year = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)
    rules_by_year_arr = np.zeros((n_routes, n_years), dtype=_COMPUTE_DTYPE)

    tariff_prev = initial.copy()
    t_years = time.perf_counter()
    rule_by_year_ms = 0
    for year_index, _year in enumerate(years):
        turnover_column = turnover_coef[:, year_index]
        if year_index == 0:
            charge_by_year[:, year_index] = np.round(initial * turnover_column, 2)
            continue

        base_coef = base_coef_arr[year_index]
        if not has_rules:
            tariff_current = np.round(tariff_prev * base_coef, 2)
            base_inc = np.round(tariff_prev * (base_coef - 1.0) * turnover_column, 2)
        else:
            rules_column = rules_coef[:, year_index]
            tariff_current = np.round(
                tariff_prev * (base_coef + rules_column - 1.0),
                2,
            )
            base_inc = np.round(tariff_prev * (base_coef - 1.0) * turnover_column, 2)
            rules_inc = np.round(tariff_prev * (rules_column - 1.0) * turnover_column, 2)
            rules_by_year_arr[:, year_index] = rules_inc

            if rule_by_year_arr is not None:
                t_rule_slice = time.perf_counter()
                for rule_index, mask in enumerate(rule_masks):
                    effective = rule_effective_by_year[rule_index][year_index]
                    rule_by_year_arr[rule_index, mask, year_index] = np.round(
                        tariff_prev[mask] * (effective - 1.0) * turnover_column[mask],
                        2,
                    )
                rule_by_year_ms += int((time.perf_counter() - t_rule_slice) * 1000)

        charge_by_year[:, year_index] = np.round(tariff_current * turnover_column, 2)
        base_by_year[:, year_index] = base_inc
        tariff_prev = tariff_current

    timings["years_loop_ms"] = int((time.perf_counter() - t_years) * 1000)
    timings["rule_by_year_ms"] = rule_by_year_ms

    t_totals = time.perf_counter()
    charge_sums = charge_by_year.sum(axis=0, dtype=np.float64)
    base_sums = base_by_year.sum(axis=0, dtype=np.float64)
    rules_sums = rules_by_year_arr.sum(axis=0, dtype=np.float64)
    global_totals = GlobalTotals()
    baseline = initial * turnover_coef[:, 0]
    global_totals.baseline_total = _to_decimal(float(baseline.sum(dtype=np.float64)))
    for year_index, year in enumerate(years):
        global_totals.charge_by_year[year] = _to_decimal(
            float(charge_sums[year_index]),
        )
        if year_index == 0:
            continue
        global_totals.base_by_year[year] = _to_decimal(float(base_sums[year_index]))
        global_totals.rules_by_year[year] = _to_decimal(float(rules_sums[year_index]))
    timings["totals_ms"] = int((time.perf_counter() - t_totals) * 1000)

    volume_fallout_by_year: np.ndarray | None = None
    money_fallout_by_year: np.ndarray | None = None
    if scenario is not None and model_rows is not None:
        from calculations.domain.services.elasticity_fallout_compute import (
            compute_fallout_arrays,
        )

        t_fallout = time.perf_counter()
        volume_fallout_by_year, money_fallout_by_year = compute_fallout_arrays(
            sidecar,
            scenario=scenario,
            years=years,
            initial_charge=initial,
            charge_by_year=charge_by_year,
            turnover_coef=turnover_coef,
            model_rows=model_rows,
            dimension_labels=dimension_labels,
        )
        timings["elasticity_fallout_ms"] = int((time.perf_counter() - t_fallout) * 1000)

    arrays = FullComputeArrays(
        initial=initial,
        base_by_year=base_by_year,
        rules_by_year_arr=rules_by_year_arr,
        charge_by_year=charge_by_year,
        rule_meta=rule_meta,
        rule_by_year=rule_by_year_arr,
        turnover_coef=turnover_coef if consider_turnover_changes else None,
        volume_fallout_by_year=volume_fallout_by_year,
        money_fallout_by_year=money_fallout_by_year,
    )
    return global_totals, timings, arrays
