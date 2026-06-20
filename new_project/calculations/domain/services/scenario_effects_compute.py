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
from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from calculations.domain.services.tariff_load import ScenarioTariffContext, TariffLoadService


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
) -> tuple[GlobalTotals, dict[str, int]]:
    import time

    timings: dict[str, int] = {}
    if isinstance(sidecar, MartSidecarView):
        if sidecar.empty:
            return GlobalTotals(), timings
    elif sidecar.empty:
        return GlobalTotals(), timings

    initial = _sidecar_charge_array(sidecar)
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

    global_totals = GlobalTotals()
    global_totals.baseline_total = _to_decimal(float(initial.sum(dtype=np.float64)))
    global_totals.charge_by_year[years[0]] = global_totals.baseline_total

    prev = initial.copy()
    current = np.empty_like(prev)
    t_years = time.perf_counter()
    for year_index, year in enumerate(years):
        if year_index == 0:
            continue

        base_coef = base_coef_arr[year_index]
        if not has_rules:
            np.multiply(prev, base_coef, out=current)
            np.round(current, 2, out=current)
            base_inc = np.round(prev * (base_coef - 1.0), 2)
            rules_inc_sum = 0.0
        else:
            rules_column = rules_coef[:, year_index]
            np.multiply(prev, base_coef + rules_column - 1.0, out=current)
            np.round(current, 2, out=current)
            base_inc = np.round(prev * (base_coef - 1.0), 2)
            rules_inc_sum = float(
                np.round(prev * (rules_column - 1.0), 2).sum(dtype=np.float64),
            )

        global_totals.charge_by_year[year] = _to_decimal(
            float(current.sum(dtype=np.float64)),
        )
        global_totals.base_by_year[year] = _to_decimal(float(base_inc.sum(dtype=np.float64)))
        if has_rules:
            global_totals.rules_by_year[year] = _to_decimal(rules_inc_sum)

        prev, current = current, prev

    timings["years_loop_ms"] = int((time.perf_counter() - t_years) * 1000)
    timings["rule_by_year_ms"] = 0
    timings["totals_ms"] = 0
    return global_totals, timings


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

    prev = initial.copy()
    t_years = time.perf_counter()
    rule_by_year_ms = 0
    for year_index, _year in enumerate(years):
        if year_index == 0:
            charge_by_year[:, year_index] = prev
            continue

        base_coef = base_coef_arr[year_index]
        if not has_rules:
            current = np.round(prev * base_coef, 2)
            base_inc = np.round(prev * (base_coef - 1.0), 2)
        else:
            rules_column = rules_coef[:, year_index]
            current = np.round(prev * (base_coef + rules_column - 1.0), 2)
            base_inc = np.round(prev * (base_coef - 1.0), 2)
            rules_inc = np.round(prev * (rules_column - 1.0), 2)
            rules_by_year_arr[:, year_index] = rules_inc

            if rule_by_year_arr is not None:
                t_rule_slice = time.perf_counter()
                for rule_index, mask in enumerate(rule_masks):
                    effective = rule_effective_by_year[rule_index][year_index]
                    rule_by_year_arr[rule_index, mask, year_index] = np.round(
                        prev[mask] * (effective - 1.0),
                        2,
                    )
                rule_by_year_ms += int((time.perf_counter() - t_rule_slice) * 1000)

        charge_by_year[:, year_index] = current
        base_by_year[:, year_index] = base_inc
        prev = current

    timings["years_loop_ms"] = int((time.perf_counter() - t_years) * 1000)
    timings["rule_by_year_ms"] = rule_by_year_ms

    t_totals = time.perf_counter()
    charge_sums = charge_by_year.sum(axis=0, dtype=np.float64)
    base_sums = base_by_year.sum(axis=0, dtype=np.float64)
    rules_sums = rules_by_year_arr.sum(axis=0, dtype=np.float64)
    global_totals = GlobalTotals()
    global_totals.baseline_total = _to_decimal(float(initial.sum(dtype=np.float64)))
    for year_index, year in enumerate(years):
        global_totals.charge_by_year[year] = _to_decimal(
            float(charge_sums[year_index]),
        )
        if year_index == 0:
            continue
        global_totals.base_by_year[year] = _to_decimal(float(base_sums[year_index]))
        global_totals.rules_by_year[year] = _to_decimal(float(rules_sums[year_index]))
    timings["totals_ms"] = int((time.perf_counter() - t_totals) * 1000)

    arrays = FullComputeArrays(
        initial=initial,
        base_by_year=base_by_year,
        rules_by_year_arr=rules_by_year_arr,
        charge_by_year=charge_by_year,
        rule_meta=rule_meta,
        rule_by_year=rule_by_year_arr,
    )
    return global_totals, timings, arrays
