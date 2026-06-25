from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np

from calculations.domain.services.route_mart_store import (
    MartMeta,
    load_mart_meta,
    load_mart_sidecar,
    load_route_mart_parquet,
    ensure_compute_sidecars,
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
    retention_coefficient_mode: str = "relative_to_base"
    consider_enterprise_load: bool = True
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

        parquet_path = Path(job.parquet_path)
        if not ensure_compute_sidecars(parquet_path):
            logger.error(
                "Deferred compute aborted: sidecars incomplete for %s",
                parquet_path,
            )
            return

        sidecar, _sidecar_timings = load_mart_sidecar(
            parquet_path,
            include_charge=True,
            include_volume=True,
        )
        if sidecar.empty or "freight_charge_rub" not in sidecar:
            logger.error(
                "Deferred compute aborted: charge sidecar missing for %s",
                parquet_path,
            )
            return
        mart_meta = job.mart_meta or load_mart_meta(parquet_path)

        scenario_stub = _elasticity_scenario_stub(job)

        _global_totals, _timings, arrays = compute_arrays_full(
            sidecar,
            years=job.years,
            base_coef_by_year=job.base_coef_by_year,
            rule_specs=job.rule_specs,
            route_set_id=job.route_set_id,
            mart_meta=mart_meta,
            mask_cache_dir=Path(job.mask_cache_dir_path),
            include_rule_by_year=job.include_rule_breakdown,
            consider_turnover_changes=job.consider_turnover_changes,
            scenario=scenario_stub,
            model_rows=job.model_rows,
            dimension_labels=(
                mart_meta.dimension_labels if mart_meta is not None else None
            ),
        )
        if arrays is None:
            return

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

        dimensions, dimension_labels, volume = prepare_compact_inputs(
            compact_df,
            mart_meta,
        )
        route_ids = None
        if "route_id" in compact_df.columns:
            route_ids = compact_df["route_id"].to_numpy(dtype=np.int32, copy=False)
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
            volume_fallout_by_year=arrays.volume_fallout_by_year,
            money_fallout_by_year=arrays.money_fallout_by_year,
        )
        if _job_data_version_stale(job):
            return
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
            phase="done",
        )
    except Exception:
        logger.exception(
            "Deferred full compute failed for scenario_id=%s cache_key=%s",
            job.scenario_id,
            job.cache_key,
        )
        from calculations.domain.services.scenario_warm_status import mark_warm_error

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
