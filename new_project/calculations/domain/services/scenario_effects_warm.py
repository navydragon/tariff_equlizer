from __future__ import annotations

import logging
from pathlib import Path
from typing import Literal

from calculations.domain.services.route_effects_loader import fetch_route_set_stats
from calculations.domain.services.route_mask_cache import mask_cache_dir
from calculations.domain.services.route_mart_store import (
    ensure_compute_sidecars,
    load_mart_meta,
    load_mart_sidecar,
    mart_meta_path,
    resolve_mart_parquet_path,
)
from calculations.domain.services.rule_mask_prewarm import prewarm_rule_mask
from calculations.domain.services.scenario_compute_store import (
    purge_stale_scenario_compute,
    save_scenario_compute_kpi_only,
)
from calculations.domain.services.scenario_effects_cache import compute_scenario_data_version
from calculations.domain.services.scenario_effects_compute import (
    compute_kpi_totals,
    rule_specs_from_context,
)
from calculations.domain.services.scenario_effects_deferred import (
    schedule_deferred_full_compute,
)
from calculations.domain.services.scenario_effects_pandas import ScenarioEffectsPandasService
from calculations.domain.services.scenario_warm_status import (
    mark_warm_error,
    resolve_warm_data_version,
    update_warm_status,
)
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario, TariffRule

logger = logging.getLogger(__name__)


def _resolve_ready_parquet_path(*, route_set_id: int) -> Path | None:
    parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    if not parquet_path.is_file() or not mart_meta_path(parquet_path).is_file():
        return None
    if not ensure_compute_sidecars(parquet_path):
        return None
    return parquet_path


def warm_scenario_kpi_snapshot(*, scenario_id: int) -> None:
    """Прогревает KPI-снимок сценария (deploy / refresh_deploy_caches --warm-scenarios)."""
    warm_scenario_after_rule_change(
        scenario_id=scenario_id,
        change="create",
        mask_changed=False,
    )


def warm_scenario_after_rule_change(
    *,
    scenario_id: int,
    change: Literal["create", "update", "delete"],
    rule_id: int | None = None,
    mask_changed: bool = False,
) -> None:
    try:
        scenario = Scenario.objects.select_related("route_set").get(pk=scenario_id)
    except Scenario.DoesNotExist:
        return

    if not scenario.route_set_id:
        return

    data_version = resolve_warm_data_version(scenario_id=scenario_id)
    if not data_version:
        return

    try:
        if mask_changed and rule_id is not None:
            update_warm_status(
                scenario_id=scenario_id,
                data_version=data_version,
                mask_changed=True,
                rule_id=rule_id,
                phase="mask",
            )
            try:
                rule = TariffRule.objects.get(pk=rule_id, scenario_id=scenario_id)
                prewarm_result = prewarm_rule_mask(rule=rule)
            except TariffRule.DoesNotExist:
                prewarm_result = None
            update_warm_status(
                scenario_id=scenario_id,
                phase="kpi",
                matched_routes=(
                    prewarm_result.matched_routes if prewarm_result is not None else None
                ),
            )
        else:
            update_warm_status(
                scenario_id=scenario_id,
                data_version=data_version,
                mask_changed=False,
                rule_id=rule_id,
                phase="kpi",
            )

        parquet_path = _resolve_ready_parquet_path(route_set_id=scenario.route_set_id)
        if parquet_path is None:
            logger.debug(
                "Skip scenario warm: mart not ready scenario_id=%s change=%s",
                scenario_id,
                change,
            )
            return

        tariff_load = TariffLoadService()
        context = tariff_load.build_scenario_context(scenario)
        years = context.years
        rule_specs = rule_specs_from_context(tariff_load, context)
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        update_warm_status(scenario_id=scenario_id, data_version=data_version)

        df, _sidecar_timings = load_mart_sidecar(parquet_path, include_charge=True)
        if df.empty:
            return

        mart_meta = load_mart_meta(parquet_path)
        global_totals, early_group_snapshot, _compute_timings = compute_kpi_totals(
            df,
            years=years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=mart_meta,
            consider_turnover_changes=bool(scenario.consider_turnover_changes),
            early_group_dim="cargo_group",
        )
        filter_options = ScenarioEffectsPandasService._collect_filter_options(
            df,
            mart_meta,
        )
        if mart_meta is not None:
            skipped_charge = mart_meta.skipped_charge
            skipped_volume = mart_meta.routes_without_volume
        else:
            skipped_charge, skipped_volume = fetch_route_set_stats(scenario.route_set_id)

        save_scenario_compute_kpi_only(
            scenario_id=scenario.id,
            data_version=data_version,
            years=years,
            global_totals=global_totals,
            filter_options=filter_options,
            skipped_charge=skipped_charge,
            routes_without_volume=skipped_volume,
            early_group_snapshot=early_group_snapshot,
        )
        from calculations.domain.services.scenario_effects_cache import (
            set_scenario_effects_revision,
        )

        set_scenario_effects_revision(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        purge_stale_scenario_compute(
            scenario_id=scenario.id,
            keep_data_version=data_version,
        )
        from calculations.domain.services.route_mask_cache import (
            purge_stale_mask_cache_dirs,
        )

        resolved_mask_dir = mask_cache_dir(route_set_id=scenario.route_set_id)
        purge_stale_mask_cache_dirs(
            route_set_id=scenario.route_set_id,
            keep_cache_dir=resolved_mask_dir,
        )

        update_warm_status(scenario_id=scenario_id, phase="compact")

        deferred_job = ScenarioEffectsPandasService._build_deferred_job(
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
            include_rule_breakdown=False,
        )
        schedule_deferred_full_compute(deferred_job)
    except Exception as exc:
        logger.exception(
            "Scenario warm failed scenario_id=%s change=%s rule_id=%s",
            scenario_id,
            change,
            rule_id,
        )
        mark_warm_error(scenario_id=scenario_id, error=str(exc))
