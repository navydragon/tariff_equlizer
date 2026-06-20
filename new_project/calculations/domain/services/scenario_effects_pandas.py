from __future__ import annotations

import time
from decimal import Decimal
from pathlib import Path
import pandas as pd

from calculations.domain.dto.scenario_effects import ScenarioEffectsComputeResponseDTO
from calculations.domain.services.scenario_effects_cache import (
    CompactRouteEffects,
    ScenarioEffectsCachePayload,
    compute_scenario_data_version,
    make_cache_key,
    store_payload,
)
from calculations.domain.services.scenario_effects_compact import prepare_compact_inputs
from calculations.domain.services.scenario_effects_compute import (
    FullComputeArrays,
    compute_arrays_full,
    compute_kpi_totals,
    rule_specs_from_context,
)
from calculations.domain.services.scenario_effects_deferred import (
    DeferredFullComputeJob,
    schedule_deferred_full_compute,
)
from calculations.domain.services.scenario_effects_formatting import (
    GlobalTotals,
    build_cards_from_totals,
    format_rub,
)
from calculations.domain.services.scenario_compute_store import (
    purge_stale_scenario_compute,
    save_scenario_compute_kpi_only,
    try_load_scenario_compute,
)
from calculations.domain.services.route_effects_loader import (
    fetch_route_set_stats,
    fetch_routes_dataframe_cached_timed,
)
from calculations.domain.services.route_mask_cache import mask_cache_dir
from calculations.domain.services.route_mart_store import (
    MartMeta,
    MartSidecarView,
    load_mart_meta,
    resolve_light_mart_columns,
    resolve_mart_parquet_path,
)
from calculations.domain.services.tariff_load import TariffLoadService
from core.domain.cargo.ordering import sort_cargo_group_names, normalize_filter_options
from scenarios.models import Scenario


def _compact_meets_request(
    compact: CompactRouteEffects | None,
    *,
    include_rule_breakdown: bool,
) -> bool:
    if compact is None:
        return False
    if include_rule_breakdown and compact.rule_by_year is None:
        return False
    return True


class ScenarioEffectsPandasService:
    def __init__(self) -> None:
        self._tariff_load = TariffLoadService()

    def compute_pandas(
        self,
        *,
        scenario: Scenario,
        user_id: int,
        include_rule_breakdown: bool = False,
    ) -> tuple[ScenarioEffectsComputeResponseDTO | None, list[str], dict]:
        started = time.perf_counter()
        context = self._tariff_load.build_scenario_context(scenario)
        t_context = time.perf_counter()
        years = context.years
        rule_specs = rule_specs_from_context(self._tariff_load, context)
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
        deferred_job: DeferredFullComputeJob | None = None
        mart_meta: MartMeta | None = None

        if scenario_bundle is not None:
            compact = scenario_bundle.compact
            global_totals = scenario_bundle.global_totals
            filter_options = scenario_bundle.filter_options
            skipped_charge = scenario_bundle.skipped_charge
            skipped_volume = scenario_bundle.routes_without_volume
            compact_ready = _compact_meets_request(
                compact,
                include_rule_breakdown=include_rule_breakdown,
            )
            t_load = t_compute = t_post_compute = time.perf_counter()
            if not compact_ready:
                parquet_path = resolve_mart_parquet_path(
                    route_set_id=scenario.route_set_id,
                )
                mart_meta = (
                    load_mart_meta(parquet_path)
                    if parquet_path.is_file()
                    else None
                )
                deferred_job = self._build_deferred_job(
                    scenario=scenario,
                    context=context,
                    years=years,
                    rule_specs=rule_specs,
                    data_version=data_version,
                    global_totals=global_totals,
                    filter_options=filter_options,
                    skipped_charge=skipped_charge,
                    routes_without_volume=skipped_volume,
                    parquet_path=parquet_path,
                    mart_meta=mart_meta,
                    include_rule_breakdown=include_rule_breakdown,
                )
        else:
            light_columns = resolve_light_mart_columns(has_rules=bool(context.rules))
            df, mart_meta, load_timings = self._load_routes_df(
                scenario,
                columns=light_columns,
            )
            t_load = time.perf_counter()

            global_totals, compute_timings = compute_kpi_totals(
                df,
                years=years,
                base_coef_by_year=context.base_coef_by_year,
                rule_specs=rule_specs,
                route_set_id=scenario.route_set_id,
                mart_meta=mart_meta,
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

            t_snapshot_save = time.perf_counter()
            save_scenario_compute_kpi_only(
                scenario_id=scenario.id,
                data_version=data_version,
                years=years,
                global_totals=global_totals,
                filter_options=filter_options,
                skipped_charge=skipped_charge,
                routes_without_volume=skipped_volume,
            )
            purge_stale_scenario_compute(
                scenario_id=scenario.id,
                keep_data_version=data_version,
            )
            scenario_snapshot_save_ms = int(
                (time.perf_counter() - t_snapshot_save) * 1000,
            )

            deferred_job = self._build_deferred_job(
                scenario=scenario,
                context=context,
                years=years,
                rule_specs=rule_specs,
                data_version=data_version,
                global_totals=global_totals,
                filter_options=filter_options,
                skipped_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                parquet_path=Path(str(load_timings.get("mart_cache_path") or "")),
                mart_meta=mart_meta,
                include_rule_breakdown=include_rule_breakdown,
            )

        cards = build_cards_from_totals(global_totals, years)
        t_cards = time.perf_counter()

        cache_key = make_cache_key(user_id=user_id, scenario_id=scenario.id)
        compact_for_cache = compact if compact_ready else None
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
                compact=compact_for_cache,
                compact_pending=deferred_job is not None,
                data_version=data_version,
            ),
        )
        t_cache = time.perf_counter()

        if deferred_job is not None:
            schedule_deferred_full_compute(
                DeferredFullComputeJob(
                    cache_key=cache_key,
                    scenario_id=deferred_job.scenario_id,
                    route_set_id=deferred_job.route_set_id,
                    data_version=deferred_job.data_version,
                    years=deferred_job.years,
                    base_coef_by_year=deferred_job.base_coef_by_year,
                    rule_specs=deferred_job.rule_specs,
                    parquet_path=deferred_job.parquet_path,
                    mask_cache_dir_path=deferred_job.mask_cache_dir_path,
                    mart_meta=deferred_job.mart_meta,
                    global_totals=deferred_job.global_totals,
                    filter_options=deferred_job.filter_options,
                    skipped_charge=deferred_job.skipped_charge,
                    routes_without_volume=deferred_job.routes_without_volume,
                    include_rule_breakdown=deferred_job.include_rule_breakdown,
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
            "include_rule_breakdown": include_rule_breakdown,
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
        *,
        columns: list[str] | None = None,
    ) -> tuple[MartSidecarView | pd.DataFrame, MartMeta | None, dict[str, int | str]]:
        route_set_id = scenario.route_set_id
        df, mart_meta, load_timings = fetch_routes_dataframe_cached_timed(
            route_set_id,
            columns=columns,
        )
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

    @staticmethod
    def _build_deferred_job(
        *,
        scenario: Scenario,
        context,
        years: list[int],
        rule_specs,
        data_version: str,
        global_totals: GlobalTotals,
        filter_options: dict[str, list[str]],
        skipped_charge: int,
        routes_without_volume: int,
        parquet_path: Path,
        mart_meta: MartMeta | None,
        include_rule_breakdown: bool = False,
    ) -> DeferredFullComputeJob:
        return DeferredFullComputeJob(
            cache_key="",
            scenario_id=scenario.id,
            route_set_id=scenario.route_set_id,
            data_version=data_version,
            years=years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            parquet_path=str(parquet_path),
            mask_cache_dir_path=str(mask_cache_dir(route_set_id=scenario.route_set_id)),
            mart_meta=mart_meta,
            global_totals=global_totals,
            filter_options=filter_options,
            skipped_charge=skipped_charge,
            routes_without_volume=routes_without_volume,
            include_rule_breakdown=include_rule_breakdown,
        )

    def _compute_arrays(
        self,
        sidecar: MartSidecarView | pd.DataFrame,
        context,
        years: list[int],
        *,
        scenario: Scenario,
        mart_meta: MartMeta | None,
        data_version: str,
    ) -> tuple[GlobalTotals, dict[str, int], FullComputeArrays | None]:
        rule_specs = rule_specs_from_context(self._tariff_load, context)
        return compute_arrays_full(
            sidecar,
            years=years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=mart_meta,
        )

    @staticmethod
    def _collect_filter_options(
        sidecar: MartSidecarView | pd.DataFrame,
        mart_meta: MartMeta | None,
    ) -> dict[str, list[str]]:
        if mart_meta is not None and mart_meta.filter_options:
            return normalize_filter_options(mart_meta.filter_options)
        if isinstance(sidecar, MartSidecarView):
            if sidecar.empty:
                return {"cargo_groups": ["—"], "holdings": ["Прочие"]}
            if mart_meta is not None and mart_meta.dimension_labels:
                cargo_groups = set(mart_meta.dimension_labels.get("cargo_group", []))
                cargo_groups.add("—")
                holdings = set(mart_meta.dimension_labels.get("holding", [])) or {"Прочие"}
                return normalize_filter_options({
                    "cargo_groups": sort_cargo_group_names(cargo_groups),
                    "holdings": sorted(holdings),
                })
            return {"cargo_groups": ["—"], "holdings": ["Прочие"]}
        if sidecar.empty:
            return {"cargo_groups": ["—"], "holdings": ["Прочие"]}

        cargo_groups = set(sidecar["cargo_group"].dropna().astype(str).tolist())
        cargo_groups.add("—")
        holdings = set(sidecar["holding"].dropna().astype(str).tolist())
        return normalize_filter_options({
            "cargo_groups": sort_cargo_group_names(cargo_groups),
            "holdings": sorted(holdings),
        })

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

        global_totals, timings, arrays = self._compute_arrays(
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
        if arrays is None:
            return None, global_totals, timings

        t_compact = time.perf_counter()
        dimensions, dimension_labels, volume = prepare_compact_inputs(
            df,
            mart_meta,
        )
        timings["compact_prep_ms"] = int((time.perf_counter() - t_compact) * 1000)
        t_build = time.perf_counter()
        compact = build_compact_from_arrays(
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
        timings["compact_build_ms"] = int((time.perf_counter() - t_build) * 1000)
        return compact, global_totals, timings

    def _compute_kpi_totals(
        self,
        sidecar: MartSidecarView | pd.DataFrame,
        context,
        years: list[int],
        *,
        scenario: Scenario,
        mart_meta: MartMeta | None,
    ) -> tuple[GlobalTotals, dict[str, int]]:
        rule_specs = rule_specs_from_context(self._tariff_load, context)
        return compute_kpi_totals(
            sidecar,
            years=years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=mart_meta,
        )
