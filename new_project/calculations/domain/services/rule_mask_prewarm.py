from __future__ import annotations

import logging
import time
from dataclasses import dataclass

from calculations.domain.services.pandas_tariff_conditions import build_rule_mask_numpy
from calculations.domain.services.route_mask_cache import save_rule_mask
from calculations.domain.services.route_mart_store import (
    ensure_compute_sidecars,
    load_mart_meta,
    load_mart_sidecar_dataframe,
    mart_meta_path,
    resolve_mart_parquet_path,
)
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario, TariffRule

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class PrewarmResult:
    ok: bool
    matched_routes: int = 0
    elapsed_ms: int = 0


def prewarm_rule_mask(*, rule: TariffRule) -> PrewarmResult | None:
    """Строит и сохраняет маску правила на диск, если витрина маршрутов уже есть."""
    started = time.perf_counter()
    try:
        rule = (
            TariffRule.objects.select_related("scenario")
            .prefetch_related("conditions")
            .get(pk=rule.pk)
        )
    except TariffRule.DoesNotExist:
        return None

    scenario = rule.scenario
    route_set_id = scenario.route_set_id
    if not route_set_id:
        return None

    parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    if not parquet_path.is_file() or not mart_meta_path(parquet_path).is_file():
        return None

    if not ensure_compute_sidecars(parquet_path):
        return None

    df, _timings = load_mart_sidecar_dataframe(parquet_path, include_charge=False)
    if df.empty:
        return None

    mart_meta = load_mart_meta(parquet_path)
    conditions = TariffLoadService._rule_conditions_payload(rule)
    mask = build_rule_mask_numpy(df, conditions, mart_meta=mart_meta).astype(
        bool,
        copy=False,
    )
    save_rule_mask(
        route_set_id=route_set_id,
        rule_id=rule.id,
        conditions=conditions,
        mask=mask,
    )
    elapsed_ms = max(0, int((time.perf_counter() - started) * 1000))
    return PrewarmResult(
        ok=True,
        matched_routes=int(mask.sum()),
        elapsed_ms=elapsed_ms,
    )


def prewarm_rules_for_route_set(*, route_set_id: int) -> int:
    """Прогревает маски всех правил сценариев набора маршрутов."""
    scenario_ids = Scenario.objects.filter(route_set_id=route_set_id).values_list(
        "id",
        flat=True,
    )
    if not scenario_ids:
        return 0

    rules = TariffRule.objects.filter(scenario_id__in=scenario_ids).prefetch_related(
        "conditions",
    )
    prewarmed = 0
    for rule in rules:
        try:
            result = prewarm_rule_mask(rule=rule)
            if result is not None and result.ok:
                prewarmed += 1
        except Exception:
            logger.exception(
                "Failed to prewarm rule mask rule_id=%s route_set_id=%s",
                rule.id,
                route_set_id,
            )
    return prewarmed
