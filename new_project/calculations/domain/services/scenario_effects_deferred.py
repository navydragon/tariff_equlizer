from __future__ import annotations

import logging
import threading
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

from calculations.domain.services.route_mart_store import (
    MartMeta,
    load_mart_meta,
    load_mart_sidecar_dataframe,
    load_route_mart_parquet,
    resolve_light_mart_columns,
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
        df, _sidecar_timings = load_mart_sidecar_dataframe(
            parquet_path,
            include_charge=True,
        )
        if df.empty or "freight_charge_rub" not in df.columns:
            light_columns = resolve_light_mart_columns(
                has_rules=bool(job.rule_specs),
            )
            df = load_route_mart_parquet(parquet_path, columns=light_columns)
        mart_meta = job.mart_meta or load_mart_meta(parquet_path)

        _global_totals, _timings, arrays = compute_arrays_full(
            df,
            years=job.years,
            base_coef_by_year=job.base_coef_by_year,
            rule_specs=job.rule_specs,
            route_set_id=job.route_set_id,
            mart_meta=mart_meta,
            mask_cache_dir=Path(job.mask_cache_dir_path),
        )
        if arrays is None:
            return

        df_full = load_route_mart_parquet(parquet_path)
        dimensions, dimension_labels, volume = prepare_compact_inputs(
            df_full,
            mart_meta,
        )
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
    except Exception:
        logger.exception(
            "Deferred full compute failed for scenario_id=%s cache_key=%s",
            job.scenario_id,
            job.cache_key,
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
    lock = _deferred_lock_for(job)
    if not lock.acquire(blocking=False):
        return

    def runner() -> None:
        try:
            _run_deferred_full_compute(job)
        finally:
            lock.release()

    thread = threading.Thread(
        target=runner,
        name=f"full-compute-{job.scenario_id}",
        daemon=True,
    )
    thread.start()


# Backward-compatible alias
DeferredCompactJob = DeferredFullComputeJob
schedule_deferred_compact = schedule_deferred_full_compute
