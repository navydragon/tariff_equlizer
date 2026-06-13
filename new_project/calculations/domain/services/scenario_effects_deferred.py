from __future__ import annotations

import logging
import threading
from dataclasses import dataclass

import numpy as np

from calculations.domain.services.scenario_compute_store import (
    ScenarioComputeBundle,
    save_scenario_compute,
)
from calculations.domain.services.scenario_effects_cache import (
    update_payload_compact,
)
from calculations.domain.services.scenario_effects_compact import (
    build_compact_from_arrays,
)
from calculations.domain.services.scenario_effects_formatting import GlobalTotals

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class DeferredCompactJob:
    cache_key: str
    scenario_id: int
    data_version: str
    years: list[int]
    initial: np.ndarray
    base_by_year: np.ndarray
    rules_by_year_arr: np.ndarray
    charge_by_year: np.ndarray
    rule_meta: list[tuple[int, str]]
    rule_by_year: np.ndarray | None
    dimensions: dict[str, np.ndarray]
    dimension_labels: dict[str, list[str]]
    volume: np.ndarray
    global_totals: GlobalTotals
    filter_options: dict[str, list[str]]
    skipped_charge: int
    routes_without_volume: int


def _run_deferred_compact(job: DeferredCompactJob) -> None:
    try:
        compact = build_compact_from_arrays(
            years=job.years,
            initial=job.initial,
            base_by_year=job.base_by_year,
            rules_by_year_arr=job.rules_by_year_arr,
            charge_by_year=job.charge_by_year,
            rule_meta=job.rule_meta,
            rule_by_year=job.rule_by_year,
            dimensions=job.dimensions,
            dimension_labels=job.dimension_labels,
            volume=job.volume,
        )
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
        update_payload_compact(cache_key=job.cache_key, compact=compact)
    except Exception:
        logger.exception(
            "Deferred compact build failed for scenario_id=%s cache_key=%s",
            job.scenario_id,
            job.cache_key,
        )


def schedule_deferred_compact(job: DeferredCompactJob) -> None:
    thread = threading.Thread(
        target=_run_deferred_compact,
        args=(job,),
        name=f"compact-{job.scenario_id}",
        daemon=True,
    )
    thread.start()
