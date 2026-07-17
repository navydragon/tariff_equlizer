from __future__ import annotations

import logging
import threading
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np

from calculations.domain.services.route_mart_store import (
    MartMeta,
    filter_sidecar_ignore_own_axles,
    load_mart_meta,
    load_mart_sidecar,
    load_route_mart_parquet,
)
from calculations.domain.services.scenario_compute_store import (
    ScenarioComputeBundle,
    save_scenario_compute,
)
from calculations.domain.services.scenario_effects_cache import (
    update_payload_compact,
)
from calculations.domain.services.scenario_effects_compact import (
    build_compact_from_arrays,
    prepare_compact_inputs,
)
from calculations.domain.services.scenario_effects_compute import (
    RuleComputeSpec,
    compute_arrays_full,
)
from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from calculations.domain.services.scenario_warm_timing import (
    format_warm_timings_message,
    log_warm_timings,
)

logger = logging.getLogger(__name__)

_deferred_locks_guard = threading.Lock()
_deferred_locks: dict[tuple[int, str], threading.Lock] = {}
_pending_jobs: dict[tuple[int, str], DeferredFullComputeJob] = {}


@dataclass(frozen=True)
class _ElasticityScenarioStub:
    consider_demand_elasticity: bool
    elasticity_set_id: int | None
    retention_coefficient_mode: str
    consider_enterprise_load: bool

    class RetentionCoefficientMode:
        COMBINED = "combined"
        RELATIVE_TO_BASE = "relative_to_base"
        ABSOLUTE = "absolute"


def _elasticity_scenario_stub(job: DeferredFullComputeJob) -> _ElasticityScenarioStub:
    return _ElasticityScenarioStub(
        consider_demand_elasticity=bool(job.consider_demand_elasticity),
        elasticity_set_id=job.elasticity_set_id,
        retention_coefficient_mode=job.retention_coefficient_mode,
        consider_enterprise_load=bool(job.consider_enterprise_load),
    )


@dataclass
class DeferredFullComputeJob:
    cache_key: str
    scenario_id: int
    route_set_id: int
    data_version: str
    years: list[int]
    base_coef_by_year: dict[int, Decimal]
    rule_specs: list[RuleComputeSpec]
    parquet_path: str
    mask_cache_dir_path: str
    mart_meta: MartMeta | None
    global_totals: GlobalTotals
    filter_options: dict[str, list[str]]
    skipped_charge: int
    routes_without_volume: int
    include_rule_breakdown: bool = False
    consider_turnover_changes: bool = False
    consider_demand_elasticity: bool = False
    elasticity_set_id: int | None = None
    retention_coefficient_mode: str = "combined"
    consider_enterprise_load: bool = True
    ignore_own_axles_cargo: bool = False
    model_rows: list = None

    def __post_init__(self) -> None:
        if self.model_rows is None:
            self.model_rows = []


def _job_data_version_stale(job: DeferredFullComputeJob) -> bool:
    from calculations.domain.services.scenario_compute_store import (
        METADATA_FILENAME,
        scenario_compute_cache_root,
    )

    scenario_dir = scenario_compute_cache_root() / str(job.scenario_id)
    if not scenario_dir.is_dir():
        return False

    for child in scenario_dir.iterdir():
        if not child.is_dir() or child.name == job.data_version:
            continue
        if (child / METADATA_FILENAME).is_file():
            return True
    return False


def _run_deferred_full_compute(job: DeferredFullComputeJob) -> None:
    try:
        if _job_data_version_stale(job):
            return

        started = time.perf_counter()
        phases: dict[str, int] = {}
        detail: dict[str, int | str] = {}

        parquet_path = Path(job.parquet_path)
        if not parquet_path.is_file():
            # Job мог быть собран во время rebuild витрины; пере-разрешаем актуальный parquet
            # без обращения к БД (важно для sqlite/tests, чтобы не ловить table locked).
            try:
                parent = parquet_path.parent
                if parent.is_dir():
                    candidates = list(parent.glob("*.parquet"))
                    if candidates:
                        parquet_path = max(candidates, key=lambda p: p.stat().st_mtime)
                        detail["parquet_path_refreshed"] = 1
            except Exception:
                pass

        t_sidecar = time.perf_counter()
        sidecar, sidecar_timings = load_mart_sidecar(
            parquet_path,
            include_charge=True,
            include_volume=True,
        )
        phases["sidecar_charge_load_ms"] = int((time.perf_counter() - t_sidecar) * 1000)
        detail.update(sidecar_timings)
        mart_meta = job.mart_meta or load_mart_meta(parquet_path)

        if sidecar.empty or "freight_charge_rub" not in sidecar:
            # Fallback: прочитать нужные колонки прямо из parquet.
            fallback_df = None
            try:
                fallback_df = load_route_mart_parquet(
                    parquet_path,
                    columns=["freight_charge_rub", "transport_volume_tons"],
                )
            except Exception:
                fallback_df = None
            if (
                fallback_df is None
                or fallback_df.empty
                or "freight_charge_rub" not in fallback_df.columns
            ):
                logger.error(
                    "Deferred compute aborted: charge sidecar missing for %s",
                    parquet_path,
                )
                return
            detail["sidecar_fallback"] = 1
            sidecar = fallback_df
        keep_mask: np.ndarray | None = None
        if job.ignore_own_axles_cargo:
            sidecar, keep_mask = filter_sidecar_ignore_own_axles(
                sidecar,
                mart_meta=mart_meta,
            )

        scenario_stub = _elasticity_scenario_stub(job)

        t_compute = time.perf_counter()
        _global_totals, compute_timings, arrays = compute_arrays_full(
            sidecar,
            years=job.years,
            base_coef_by_year=job.base_coef_by_year,
            rule_specs=job.rule_specs,
            route_set_id=job.route_set_id,
            mart_meta=mart_meta,
            mask_cache_dir=Path(job.mask_cache_dir_path),
            include_rule_by_year=job.include_rule_breakdown,
            consider_turnover_changes=job.consider_turnover_changes,
            include_fallout=False,
            scenario=scenario_stub,
            model_rows=job.model_rows,
            dimension_labels=(
                mart_meta.dimension_labels if mart_meta is not None else None
            ),
        )
        phases["compute_full_ms"] = int((time.perf_counter() - t_compute) * 1000)
        detail.update(compute_timings)
        if arrays is None:
            return

        t_volume = time.perf_counter()
        volume_sidecar, volume_timings = load_mart_sidecar(
            parquet_path,
            include_charge=False,
            include_volume=True,
        )
        detail.update(volume_timings)
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

        if keep_mask is not None and len(keep_mask) == len(compact_df):
            compact_df = compact_df.loc[keep_mask].reset_index(drop=True)

        dimensions, dimension_labels, volume = prepare_compact_inputs(
            compact_df,
            mart_meta,
        )
        route_ids = None
        if "route_id" in compact_df.columns:
            route_ids = compact_df["route_id"].to_numpy(dtype=np.int32, copy=False)
        phases["compact_prep_ms"] = int((time.perf_counter() - t_volume) * 1000)

        t_compact = time.perf_counter()
        compact = build_compact_from_arrays(
            years=job.years,
            initial=arrays.initial,
            base_by_year=arrays.base_by_year,
            rules_by_year_arr=arrays.rules_by_year_arr,
            charge_by_year=arrays.charge_by_year,
            rule_meta=arrays.rule_meta,
            rule_by_year=arrays.rule_by_year,
            dimensions=dimensions,
            dimension_labels=dimension_labels,
            volume=volume,
            route_ids=route_ids,
            turnover_coef=arrays.turnover_coef,
            volume_fallout_by_year=None,
            money_fallout_by_year=None,
        )
        phases["compact_build_ms"] = int((time.perf_counter() - t_compact) * 1000)
        if _job_data_version_stale(job):
            return

        t_save = time.perf_counter()
        save_scenario_compute(
            scenario_id=job.scenario_id,
            data_version=job.data_version,
            bundle=ScenarioComputeBundle(
                compact=compact,
                global_totals=job.global_totals,
                filter_options=job.filter_options,
                skipped_charge=job.skipped_charge,
                routes_without_volume=job.routes_without_volume,
            ),
        )
        phases["save_compact_ms"] = int((time.perf_counter() - t_save) * 1000)
        from calculations.domain.services.scenario_effects_cache import (
            set_scenario_effects_revision,
        )

        set_scenario_effects_revision(
            scenario_id=job.scenario_id,
            data_version=job.data_version,
        )
        update_payload_compact(cache_key=job.cache_key, compact=compact)
        from calculations.domain.services.scenario_warm_status import update_warm_status

        update_warm_status(
            scenario_id=job.scenario_id,
            data_version=job.data_version,
            phase="compact",
        )

        # Эластичность (fallout) считаем отдельной фазой: compact готов сразу,
        # а массивы выпадения догружаются позже.
        if scenario_stub.consider_demand_elasticity and scenario_stub.elasticity_set_id:
            from calculations.domain.services.elasticity_fallout_compute import (
                FalloutComputeStats,
                compute_fallout_arrays,
            )
            from calculations.domain.services.scenario_compute_store import (
                compute_fallout_fingerprint,
                save_fallout_cache,
                save_scenario_fallout_arrays,
                try_load_fallout_cache,
            )
            from calculations.domain.services.scenario_effects_cache import (
                update_payload_fallout_ready,
            )
            from calculations.domain.services.scenario_effects_compute import (
                build_turnover_coef_matrix,
            )

            t_fallout = time.perf_counter()
            turnover_matrix = build_turnover_coef_matrix(
                sidecar,
                job.years,
                enabled=job.consider_turnover_changes,
            )
            fallout_fingerprint = compute_fallout_fingerprint(
                scenario=scenario_stub,
                initial_charge=arrays.initial,
                charge_by_year=arrays.charge_by_year,
                turnover_coef=turnover_matrix,
            )
            n_routes = len(arrays.initial)
            n_years = len(job.years)
            cached_fallout = try_load_fallout_cache(
                scenario_id=job.scenario_id,
                fingerprint=fallout_fingerprint,
                n_routes=n_routes,
                n_years=n_years,
            )
            if cached_fallout is not None:
                volume_fallout_by_year, money_fallout_by_year = cached_fallout
                fallout_stats = FalloutComputeStats(
                    routes_total=n_routes,
                    years_count=n_years,
                )
                detail["fallout_cache_hit"] = 1
            else:
                volume_fallout_by_year, money_fallout_by_year, fallout_stats = (
                    compute_fallout_arrays(
                        sidecar,
                        scenario=scenario_stub,
                        years=job.years,
                        initial_charge=arrays.initial,
                        charge_by_year=arrays.charge_by_year,
                        turnover_coef=turnover_matrix,
                        model_rows=job.model_rows,
                        dimension_labels=(
                            mart_meta.dimension_labels if mart_meta is not None else None
                        ),
                    )
                )
                try:
                    save_fallout_cache(
                        scenario_id=job.scenario_id,
                        fingerprint=fallout_fingerprint,
                        volume_fallout_by_year=volume_fallout_by_year,
                        money_fallout_by_year=money_fallout_by_year,
                    )
                except OSError:
                    logger.warning(
                        "Failed to persist fallout cache scenario_id=%s fingerprint=%s",
                        job.scenario_id,
                        fallout_fingerprint,
                        exc_info=True,
                    )
            detail["elasticity_fallout_ms"] = int((time.perf_counter() - t_fallout) * 1000)
            for key, value in fallout_stats.to_timings().items():
                detail[key] = int(value)

            if _job_data_version_stale(job):
                return

            t_save_fallout = time.perf_counter()
            save_scenario_fallout_arrays(
                scenario_id=job.scenario_id,
                data_version=job.data_version,
                volume_fallout_by_year=volume_fallout_by_year,
                money_fallout_by_year=money_fallout_by_year,
                fallout_cache_fingerprint=fallout_fingerprint,
            )
            phases["save_fallout_ms"] = int((time.perf_counter() - t_save_fallout) * 1000)
            set_scenario_effects_revision(
                scenario_id=job.scenario_id,
                data_version=job.data_version,
            )
            update_payload_fallout_ready(cache_key=job.cache_key)
        phases["save_ms"] = phases.get("save_compact_ms", 0) + phases.get("save_fallout_ms", 0)
        phases["total_ms"] = int((time.perf_counter() - started) * 1000)
        log_warm_timings(
            logger,
            label="compact",
            phases=phases,
            detail=detail,
            scenario_id=job.scenario_id,
            data_version=job.data_version,
            rules=len(job.rule_specs),
            include_rule_breakdown=job.include_rule_breakdown,
        )
        rebuild_message = format_warm_timings_message(
            label="compact",
            phases=phases,
            detail=detail,
            scenario_id=job.scenario_id,
            data_version=job.data_version,
            rules=len(job.rule_specs),
            include_rule_breakdown=job.include_rule_breakdown,
        )
        update_warm_status(
            scenario_id=job.scenario_id,
            data_version=job.data_version,
            phase="done",
            rebuild_message=rebuild_message,
        )
    except Exception:
        logger.exception(
            "Deferred full compute failed for scenario_id=%s cache_key=%s",
            job.scenario_id,
            job.cache_key,
        )
        from calculations.domain.services.scenario_compute_store import (
            is_scenario_compact_on_disk,
        )
        from calculations.domain.services.scenario_warm_status import (
            mark_breakdown_warm_error,
            mark_warm_error,
        )

        if job.include_rule_breakdown and is_scenario_compact_on_disk(
            scenario_id=job.scenario_id,
            data_version=job.data_version,
        ):
            mark_breakdown_warm_error(
                scenario_id=job.scenario_id,
                error="Ошибка фоновой сборки детализации",
            )
        else:
            mark_warm_error(
                scenario_id=job.scenario_id,
                error="Ошибка фоновой сборки детализации",
            )


def _deferred_lock_for(job: DeferredFullComputeJob) -> threading.Lock:
    key = (job.scenario_id, job.data_version)
    with _deferred_locks_guard:
        lock = _deferred_locks.get(key)
        if lock is None:
            lock = threading.Lock()
            _deferred_locks[key] = lock
        return lock


def is_deferred_running(scenario_id: int, data_version: str) -> bool:
    key = (scenario_id, data_version)
    with _deferred_locks_guard:
        lock = _deferred_locks.get(key)
    if lock is None:
        return False
    return lock.locked()


def schedule_deferred_full_compute(job: DeferredFullComputeJob) -> None:
    key = (job.scenario_id, job.data_version)
    lock = _deferred_lock_for(job)
    if not lock.acquire(blocking=False):
        with _deferred_locks_guard:
            pending = _pending_jobs.get(key)
            if pending is None or (
                job.include_rule_breakdown and not pending.include_rule_breakdown
            ):
                _pending_jobs[key] = job
        return

    def runner() -> None:
        follow_up: DeferredFullComputeJob | None = None
        try:
            _run_deferred_full_compute(job)
        finally:
            lock.release()
            with _deferred_locks_guard:
                pending = _pending_jobs.pop(key, None)
            if pending is not None and (
                pending.include_rule_breakdown and not job.include_rule_breakdown
            ):
                follow_up = pending
        if follow_up is not None:
            schedule_deferred_full_compute(follow_up)

    thread = threading.Thread(
        target=runner,
        name=f"full-compute-{job.scenario_id}",
        daemon=True,
    )
    thread.start()


# Backward-compatible alias
DeferredCompactJob = DeferredFullComputeJob
schedule_deferred_compact = schedule_deferred_full_compute
