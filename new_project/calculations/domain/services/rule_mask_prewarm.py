from __future__ import annotations

import logging
import os
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass

from calculations.domain.services.pandas_tariff_conditions import build_rule_mask_numpy
from calculations.domain.services.route_mask_cache import save_rule_mask
from calculations.domain.services.route_mart_store import (
    MartMeta,
    MartSidecarView,
    ensure_compute_sidecars,
    load_mart_meta,
    load_mart_sidecar,
    mart_meta_path,
    resolve_mart_parquet_path,
)
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario, TariffRule

logger = logging.getLogger(__name__)

_DEFAULT_PREWARM_WORKERS = min(8, max(1, (os.cpu_count() or 2)))


@dataclass(frozen=True)
class PrewarmResult:
    ok: bool
    matched_routes: int = 0
    elapsed_ms: int = 0


def _prewarm_rule_mask_on_sidecar(
    *,
    rule: TariffRule,
    sidecar: MartSidecarView,
    mart_meta: MartMeta | None,
    route_set_id: int,
) -> PrewarmResult:
    started = time.perf_counter()
    conditions = TariffLoadService._rule_conditions_payload(rule)
    mask = build_rule_mask_numpy(sidecar, conditions, mart_meta=mart_meta).astype(
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

    sidecar, _timings = load_mart_sidecar(parquet_path, include_charge=False)
    if sidecar.empty:
        return None

    mart_meta = load_mart_meta(parquet_path)
    result = _prewarm_rule_mask_on_sidecar(
        rule=rule,
        sidecar=sidecar,
        mart_meta=mart_meta,
        route_set_id=route_set_id,
    )
    return PrewarmResult(
        ok=result.ok,
        matched_routes=result.matched_routes,
        elapsed_ms=max(0, int((time.perf_counter() - started) * 1000)),
    )


def prewarm_rules_for_route_set(
    *,
    route_set_id: int,
    max_workers: int = _DEFAULT_PREWARM_WORKERS,
) -> dict[str, int]:
    """Прогревает маски всех правил сценариев набора маршрутов."""
    started = time.perf_counter()
    scenario_ids = Scenario.objects.filter(route_set_id=route_set_id).values_list(
        "id",
        flat=True,
    )
    if not scenario_ids:
        return {"prewarmed": 0, "elapsed_ms": 0, "sidecar_load_ms": 0}

    rules = list(
        TariffRule.objects.filter(scenario_id__in=scenario_ids).prefetch_related(
            "conditions",
        ),
    )
    if not rules:
        return {"prewarmed": 0, "elapsed_ms": 0, "sidecar_load_ms": 0}

    parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    if not parquet_path.is_file() or not mart_meta_path(parquet_path).is_file():
        return {"prewarmed": 0, "elapsed_ms": 0, "sidecar_load_ms": 0}
    if not ensure_compute_sidecars(parquet_path):
        return {"prewarmed": 0, "elapsed_ms": 0, "sidecar_load_ms": 0}

    t_sidecar = time.perf_counter()
    sidecar, _timings = load_mart_sidecar(parquet_path, include_charge=False)
    mart_meta = load_mart_meta(parquet_path)
    sidecar_load_ms = int((time.perf_counter() - t_sidecar) * 1000)
    if sidecar.empty:
        return {
            "prewarmed": 0,
            "elapsed_ms": int((time.perf_counter() - started) * 1000),
            "sidecar_load_ms": sidecar_load_ms,
        }

    prewarmed = 0
    workers = min(max_workers, len(rules))
    if workers <= 1:
        for rule in rules:
            try:
                result = _prewarm_rule_mask_on_sidecar(
                    rule=rule,
                    sidecar=sidecar,
                    mart_meta=mart_meta,
                    route_set_id=route_set_id,
                )
                if result.ok:
                    prewarmed += 1
            except Exception:
                logger.exception(
                    "Failed to prewarm rule mask rule_id=%s route_set_id=%s",
                    rule.id,
                    route_set_id,
                )
    else:
        with ThreadPoolExecutor(max_workers=workers) as executor:
            futures = {
                executor.submit(
                    _prewarm_rule_mask_on_sidecar,
                    rule=rule,
                    sidecar=sidecar,
                    mart_meta=mart_meta,
                    route_set_id=route_set_id,
                ): rule
                for rule in rules
            }
            for future in as_completed(futures):
                rule = futures[future]
                try:
                    result = future.result()
                    if result.ok:
                        prewarmed += 1
                except Exception:
                    logger.exception(
                        "Failed to prewarm rule mask rule_id=%s route_set_id=%s",
                        rule.id,
                        route_set_id,
                    )

    return {
        "prewarmed": prewarmed,
        "elapsed_ms": int((time.perf_counter() - started) * 1000),
        "sidecar_load_ms": sidecar_load_ms,
    }
