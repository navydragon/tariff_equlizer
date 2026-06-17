from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from django.core.cache import cache

from calculations.domain.services.scenario_compute_store import (
    is_scenario_compact_on_disk,
    try_load_scenario_compute,
)
from calculations.domain.services.scenario_effects_cache import (
    CACHE_TIMEOUT_SECONDS,
    compute_scenario_data_version,
)
from scenarios.models import Scenario

WarmPhase = Literal["queued", "mask", "kpi", "compact", "done", "error"]

WARM_STATUS_PREFIX = "scenario_warm"


@dataclass
class ScenarioWarmStatus:
    scenario_id: int
    phase: WarmPhase
    data_version: str
    mask_changed: bool = False
    rule_id: int | None = None
    matched_routes: int | None = None
    started_at: float = 0.0
    updated_at: float = 0.0
    error: str | None = None


def warm_status_cache_key(*, scenario_id: int) -> str:
    return f"{WARM_STATUS_PREFIX}:{scenario_id}"


def resolve_warm_data_version(*, scenario_id: int) -> str | None:
    try:
        scenario = Scenario.objects.select_related("route_set").get(pk=scenario_id)
    except Scenario.DoesNotExist:
        return None
    if not scenario.route_set_id:
        return None
    from calculations.domain.services.tariff_load import TariffLoadService

    tariff_load = TariffLoadService()
    context = tariff_load.build_scenario_context(scenario)
    return compute_scenario_data_version(
        scenario=scenario,
        base_coef_by_year=context.base_coef_by_year,
        rules=context.rules,
    )


def build_rebuild_meta(
    *,
    scenario_id: int,
    rule_id: int | None,
    mask_changed: bool,
    warm_scheduled: bool,
) -> dict[str, object]:
    if not warm_scheduled:
        return {"started": False}
    data_version = resolve_warm_data_version(scenario_id=scenario_id)
    if not data_version:
        return {"started": False}
    payload: dict[str, object] = {
        "started": True,
        "data_version": data_version,
        "mask_changed": mask_changed,
    }
    if rule_id is not None:
        payload["rule_id"] = rule_id
    return payload


def _load_status(*, scenario_id: int) -> ScenarioWarmStatus | None:
    value = cache.get(warm_status_cache_key(scenario_id=scenario_id))
    return value if isinstance(value, ScenarioWarmStatus) else None


def init_warm_status(
    *,
    scenario_id: int,
    data_version: str,
    mask_changed: bool,
    rule_id: int | None,
    phase: WarmPhase = "queued",
) -> ScenarioWarmStatus:
    now = time.time()
    status = ScenarioWarmStatus(
        scenario_id=scenario_id,
        phase=phase,
        data_version=data_version,
        mask_changed=mask_changed,
        rule_id=rule_id,
        started_at=now,
        updated_at=now,
    )
    cache.set(
        warm_status_cache_key(scenario_id=scenario_id),
        status,
        CACHE_TIMEOUT_SECONDS,
    )
    return status


def update_warm_status(*, scenario_id: int, **fields: object) -> ScenarioWarmStatus | None:
    status = _load_status(scenario_id=scenario_id)
    if status is None:
        data_version = fields.get("data_version")
        if not isinstance(data_version, str) or not data_version:
            return None
        status = init_warm_status(
            scenario_id=scenario_id,
            data_version=data_version,
            mask_changed=bool(fields.get("mask_changed", False)),
            rule_id=fields.get("rule_id") if isinstance(fields.get("rule_id"), int) else None,
            phase=fields.get("phase") if isinstance(fields.get("phase"), str) else "queued",
        )
        fields = {key: value for key, value in fields.items() if key not in {"data_version", "mask_changed", "rule_id", "phase"}}

    for key, value in fields.items():
        if hasattr(status, key):
            setattr(status, key, value)
    status.updated_at = time.time()
    cache.set(
        warm_status_cache_key(scenario_id=scenario_id),
        status,
        CACHE_TIMEOUT_SECONDS,
    )
    return status


def mark_warm_error(*, scenario_id: int, error: str) -> None:
    update_warm_status(scenario_id=scenario_id, phase="error", error=error)


def get_warm_status(*, scenario_id: int) -> dict[str, Any] | None:
    status = _load_status(scenario_id=scenario_id)
    if status is None:
        return None
    return _status_to_api(status)


def _status_to_api(status: ScenarioWarmStatus) -> dict[str, Any]:
    kpi_ready = False
    compact_ready = False
    if status.data_version:
        kpi_ready = (
            try_load_scenario_compute(
                scenario_id=status.scenario_id,
                data_version=status.data_version,
            )
            is not None
        )
        compact_ready = is_scenario_compact_on_disk(
            scenario_id=status.scenario_id,
            data_version=status.data_version,
        )

    phase: WarmPhase = status.phase
    if phase == "error":
        pass
    elif compact_ready:
        phase = "done"
    elif kpi_ready and phase in {"kpi", "queued", "mask"}:
        phase = "compact" if status.phase != "done" else "done"

    elapsed_ms = 0
    if status.started_at:
        elapsed_ms = max(0, int((time.time() - status.started_at) * 1000))

    return {
        "phase": phase,
        "data_version": status.data_version,
        "mask_changed": status.mask_changed,
        "rule_id": status.rule_id,
        "matched_routes": status.matched_routes,
        "kpi_ready": kpi_ready,
        "compact_ready": compact_ready,
        "elapsed_ms": elapsed_ms,
        "error": status.error,
    }
