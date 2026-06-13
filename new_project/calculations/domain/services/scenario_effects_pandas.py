from __future__ import annotations

import time
from decimal import Decimal

import numpy as np
import pandas as pd

from calculations.domain.dto.scenario_effects import ScenarioEffectsComputeResponseDTO
from calculations.domain.services.route_mask_cache import build_or_load_rule_mask
from calculations.domain.services.scenario_effects_cache import (
    CompactRouteEffects,
    ScenarioEffectsCachePayload,
    compute_scenario_data_version,
    make_cache_key,
    store_payload,
)
from calculations.domain.services.scenario_effects_compact import (
    _COMPUTE_DTYPE,
    _DIMENSION_COLUMNS,
    _FLOAT_DTYPE,
    extract_volume_array,
)
from calculations.domain.services.scenario_effects_deferred import (
    DeferredCompactJob,
    schedule_deferred_compact,
)
from calculations.domain.services.scenario_effects_formatting import (
    GlobalTotals,
    build_cards_from_totals,
    format_rub,
)
from calculations.domain.services.scenario_compute_store import (
    try_load_scenario_compute,
)
from calculations.domain.services.route_effects_loader import (
    fetch_route_set_stats,
    fetch_routes_dataframe_cached_timed,
)
from calculations.domain.services.route_mart_store import MartMeta
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario


def _effective_rule_coefficient(coefficient: float, base_percent: float) -> float:
    return 1.0 + (coefficient - 1.0) * base_percent / 100.0


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


class ScenarioEffectsPandasService:
    def __init__(self) -> None:
        self._tariff_load = TariffLoadService()

    def compute_pandas(
        self,
        *,
        scenario: Scenario,
        user_id: int,
    ) -> tuple[ScenarioEffectsComputeResponseDTO | None, list[str], dict]:
        started = time.perf_counter()
        context = self._tariff_load.build_scenario_context(scenario)
        t_context = time.perf_counter()
        years = context.years
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )

        t_snapshot_load = time.perf_counter()
        scenario_bundle = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        scenario_snapshot_load_ms = int((time.perf_counter() - t_snapshot_load) * 1000)
        scenario_compute_hit = scenario_bundle is not None

        load_timings: dict[str, int | str] = {}
        compute_timings: dict[str, int] = {}
        scenario_snapshot_save_ms = 0
        compact_ready = True
        deferred_job: DeferredCompactJob | None = None

        if scenario_bundle is not None:
            compact = scenario_bundle.compact
            global_totals = scenario_bundle.global_totals
            filter_options = scenario_bundle.filter_options
            skipped_charge = scenario_bundle.skipped_charge
            skipped_volume = scenario_bundle.routes_without_volume
            t_load = t_compute = t_post_compute = time.perf_counter()
        else:
            df, mart_meta, load_timings = self._load_routes_df(scenario)
            t_load = time.perf_counter()

            (
                global_totals,
                compute_timings,
                deferred_job,
            ) = self._compute_arrays(
                df,
                context,
                years,
                scenario=scenario,
                mart_meta=mart_meta,
                data_version=data_version,
            )
            compact = None
            compact_ready = False
            t_compute = time.perf_counter()

            filter_options = self._collect_filter_options(df, mart_meta)
            skipped_charge, skipped_volume = self._resolve_route_stats(
                scenario,
                mart_meta,
                load_timings,
            )
            t_post_compute = time.perf_counter()

        cards = build_cards_from_totals(global_totals, years)
        t_cards = time.perf_counter()

        cache_key = make_cache_key(user_id=user_id, scenario_id=scenario.id)
        store_payload(
            cache_key=cache_key,
            payload=ScenarioEffectsCachePayload(
                user_id=user_id,
                scenario_id=scenario.id,
                years=years,
                routes_without_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                baseline_total=global_totals.baseline_total,
                facts=[],
                compact=compact,
                compact_pending=deferred_job is not None,
                data_version=data_version,
            ),
        )
        t_cache = time.perf_counter()

        if deferred_job is not None:
            schedule_deferred_compact(
                DeferredCompactJob(
                    cache_key=cache_key,
                    scenario_id=deferred_job.scenario_id,
                    data_version=deferred_job.data_version,
                    years=deferred_job.years,
                    initial=deferred_job.initial,
                    base_by_year=deferred_job.base_by_year,
                    rules_by_year_arr=deferred_job.rules_by_year_arr,
                    charge_by_year=deferred_job.charge_by_year,
                    rule_meta=deferred_job.rule_meta,
                    rule_by_year=deferred_job.rule_by_year,
                    dimensions=deferred_job.dimensions,
                    dimension_labels=deferred_job.dimension_labels,
                    volume=deferred_job.volume,
                    global_totals=global_totals,
                    filter_options=filter_options,
                    skipped_charge=skipped_charge,
                    routes_without_volume=skipped_volume,
                ),
            )

        elapsed_ms = int((t_cache - started) * 1000)
        route_mart_hit = bool(load_timings.get("cache_hit"))
        meta = {
            "engine": "pandas",
            "elapsed_ms": elapsed_ms,
            "data_version": data_version,
            "cache_hit": scenario_compute_hit or route_mart_hit,
            "route_mart_cache_hit": route_mart_hit,
            "scenario_compute_cache_hit": scenario_compute_hit,
            "compact_ready": compact_ready,
            "mart_cache_path": load_timings.get("mart_cache_path"),
            "timings": {
                "context_ms": int((t_context - started) * 1000),
                "scenario_snapshot_load_ms": scenario_snapshot_load_ms,
                "scenario_snapshot_save_ms": scenario_snapshot_save_ms,
                "load_ms": int((t_load - t_context) * 1000),
                "compute_ms": int((t_compute - t_load) * 1000),
                "post_compute_ms": int((t_post_compute - t_compute) * 1000),
                "cards_ms": int((t_cards - t_post_compute) * 1000),
                "cache_ms": int((t_cache - t_cards) * 1000),
                **load_timings,
                **compute_timings,
            },
        }

        return (
            ScenarioEffectsComputeResponseDTO(
                cache_key=cache_key,
                scenario_id=scenario.id,
                years=years,
                baseline_rub=format_rub(global_totals.baseline_total),
                routes_without_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                cards=cards,
                filter_options=filter_options,
            ),
            [],
            meta,
        )

    def _load_routes_df(
        self,
        scenario: Scenario,
    ) -> tuple[pd.DataFrame, MartMeta | None, dict[str, int | str]]:
        route_set_id = scenario.route_set_id
        df, mart_meta, load_timings = fetch_routes_dataframe_cached_timed(route_set_id)
        return df, mart_meta, load_timings

    @staticmethod
    def _resolve_route_stats(
        scenario: Scenario,
        mart_meta: MartMeta | None,
        load_timings: dict[str, int | str],
    ) -> tuple[int, int]:
        if mart_meta is not None:
            return mart_meta.skipped_charge, mart_meta.routes_without_volume
        if "stats_ms" in load_timings:
            return 0, 0
        t_stats = time.perf_counter()
        skipped_charge, skipped_volume = fetch_route_set_stats(scenario.route_set_id)
        load_timings["stats_ms"] = int((time.perf_counter() - t_stats) * 1000)
        return skipped_charge, skipped_volume

    def _compute_arrays(
        self,
        df: pd.DataFrame,
        context,
        years: list[int],
        *,
        scenario: Scenario,
        mart_meta: MartMeta | None,
        data_version: str,
    ) -> tuple[GlobalTotals, dict[str, int], DeferredCompactJob | None]:
        timings: dict[str, int] = {}
        if df.empty:
            return GlobalTotals(), timings, None

        n_routes = len(df)
        n_years = len(years)
        initial = df["freight_charge_rub"].to_numpy(dtype=_COMPUTE_DTYPE, copy=False)
        rules_coef = np.ones((n_routes, n_years), dtype=_COMPUTE_DTYPE)
        base_coef_arr = np.array(
            [float(context.base_coef_by_year.get(year, Decimal("1"))) for year in years],
            dtype=_COMPUTE_DTYPE,
        )

        rule_meta: list[tuple[int, str]] = []
        rule_masks: list[np.ndarray] = []
        rule_effective_by_year: list[np.ndarray] = []

        t_masks = time.perf_counter()
        for rule in context.rules:
            conditions = self._tariff_load._rule_conditions_payload(rule)
            mask = build_or_load_rule_mask(
                route_set_id=scenario.route_set_id,
                rule_id=rule.id,
                conditions=conditions,
                df=df,
                mart_meta=mart_meta,
            )
            if not mask.any():
                continue

            year_coefs = {
                value.year: float(value.coefficient)
                for value in rule.year_values.all()
            }
            base_percent = float(rule.base_percent)
            effective_arr = np.array(
                [
                    _effective_rule_coefficient(year_coefs.get(year, 1.0), base_percent)
                    for year in years
                ],
                dtype=_COMPUTE_DTYPE,
            )
            rule_meta.append((rule.id, rule.name))
            rule_masks.append(mask)
            rule_effective_by_year.append(effective_arr)

            for year_index, _year in enumerate(years):
                rules_coef[mask, year_index] *= effective_arr[year_index]
        timings["masks_ms"] = int((time.perf_counter() - t_masks) * 1000)

        has_rules = bool(rule_meta)
        n_rules = len(rule_meta)
        rule_by_year_arr = (
            np.zeros((n_rules, n_routes, n_years), dtype=_COMPUTE_DTYPE)
            if n_rules
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

        dimensions: dict[str, np.ndarray] = {}
        dimension_labels: dict[str, list[str]] = {}
        if mart_meta is not None and mart_meta.dimension_labels:
            dimensions = {
                column: df[f"dim_{column}"].to_numpy(dtype=np.int32, copy=False)
                for column in _DIMENSION_COLUMNS
                if f"dim_{column}" in df.columns
            }
            dimension_labels = mart_meta.dimension_labels
        else:
            for column in _DIMENSION_COLUMNS:
                dim_column = f"dim_{column}"
                if dim_column in df.columns:
                    dimensions[column] = df[dim_column].to_numpy(
                        dtype=np.int32,
                        copy=False,
                    )
                    dimension_labels[column] = (
                        df[column].astype(str).unique().tolist()
                    )
                elif column in df.columns:
                    series = df[column].astype(str)
                    codes, uniques = pd.factorize(series, sort=False)
                    dimensions[column] = codes.astype(np.int32, copy=False)
                    dimension_labels[column] = uniques.tolist()

        volume = extract_volume_array(df)
        deferred_job = DeferredCompactJob(
            cache_key="",
            scenario_id=scenario.id,
            data_version=data_version,
            years=years,
            initial=initial,
            base_by_year=base_by_year,
            rules_by_year_arr=rules_by_year_arr,
            charge_by_year=charge_by_year,
            rule_meta=rule_meta,
            rule_by_year=rule_by_year_arr,
            dimensions=dimensions,
            dimension_labels=dimension_labels,
            volume=volume,
            global_totals=global_totals,
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
        )
        return global_totals, timings, deferred_job

    @staticmethod
    def _collect_filter_options(
        df: pd.DataFrame,
        mart_meta: MartMeta | None,
    ) -> dict[str, list[str]]:
        if mart_meta is not None and mart_meta.filter_options:
            return mart_meta.filter_options
        if df.empty:
            return {"cargo_groups": ["—"], "holdings": ["Прочие"]}

        cargo_groups = set(df["cargo_group"].dropna().astype(str).tolist())
        cargo_groups.add("—")
        holdings = set(df["holding"].dropna().astype(str).tolist())
        return {
            "cargo_groups": sorted(cargo_groups),
            "holdings": sorted(holdings),
        }

    def _compute_compact(
        self,
        df: pd.DataFrame,
        context,
        years: list[int],
        *,
        scenario: Scenario,
        mart_meta: MartMeta | None,
    ) -> tuple[CompactRouteEffects | None, GlobalTotals, dict[str, int]]:
        """Синхронный полный расчёт (для тестов и профилирования)."""
        from calculations.domain.services.scenario_effects_compact import (
            build_compact_from_arrays,
        )

        global_totals, timings, deferred_job = self._compute_arrays(
            df,
            context,
            years,
            scenario=scenario,
            mart_meta=mart_meta,
            data_version=compute_scenario_data_version(
                scenario=scenario,
                base_coef_by_year=context.base_coef_by_year,
                rules=context.rules,
            ),
        )
        if deferred_job is None:
            return None, global_totals, timings

        t_compact = time.perf_counter()
        compact = build_compact_from_arrays(
            years=deferred_job.years,
            initial=deferred_job.initial,
            base_by_year=deferred_job.base_by_year,
            rules_by_year_arr=deferred_job.rules_by_year_arr,
            charge_by_year=deferred_job.charge_by_year,
            rule_meta=deferred_job.rule_meta,
            rule_by_year=deferred_job.rule_by_year,
            dimensions=deferred_job.dimensions,
            dimension_labels=deferred_job.dimension_labels,
            volume=deferred_job.volume,
        )
        timings["compact_build_ms"] = int((time.perf_counter() - t_compact) * 1000)
        return compact, global_totals, timings
