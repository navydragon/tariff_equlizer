from __future__ import annotations

from typing import Literal

from scenarios.models import Scenario

def _build_cache_readiness_payload(*, scenario: Scenario) -> dict[str, object]:
    from calculations.domain.services.route_mart_warm_status import (
        get_route_mart_warm_status,
        is_route_mart_ready,
    )
    from calculations.domain.services.scenario_warm_status import get_warm_status

    mart_status = get_route_mart_warm_status(route_set_id=scenario.route_set_id)
    scenario_status = get_warm_status(scenario_id=scenario.id)
    mart_ready = is_route_mart_ready(route_set_id=scenario.route_set_id)
    mart_phase = mart_status["phase"] if mart_status else None
    scenario_phase = scenario_status["phase"] if scenario_status else None
    kpi_ready = bool(scenario_status and scenario_status.get("kpi_ready"))
    compact_ready = bool(scenario_status and scenario_status.get("compact_ready"))
    ready_for_compute = mart_ready and (
        scenario_status is None or kpi_ready or scenario_phase == "done"
    )

    if not mart_ready and mart_phase in {"queued", "building"}:
        message = "Пересборка витрины маршрутов…"
    elif scenario_phase == "mask":
        message = "Пересборка масок сценария…"
    elif scenario_phase == "kpi":
        message = "Обновление итогов сценария…"
    elif scenario_phase == "compact":
        message = "Детализация в фоне…"
    elif mart_phase == "error":
        message = mart_status.get("error") or "Ошибка пересборки витрины"
    elif scenario_phase == "error":
        message = scenario_status.get("error") or "Ошибка пересчёта сценария"
    else:
        message = "Данные обновляются…"

    return {
        "route_set_id": scenario.route_set_id,
        "mart_phase": mart_phase,
        "mart_ready": mart_ready,
        "scenario_phase": scenario_phase,
        "kpi_ready": kpi_ready,
        "compact_ready": compact_ready,
        "ready_for_compute": ready_for_compute,
        "message": message,
    }


DecisionEffectsStage = Literal[
    "error",
    "mart_rebuilding",
    "scenario_warming",
    "ready_for_compute",
    "compact_pending",
    "fallout_pending",
    "done",
]


def build_decision_effects_status(
    *,
    scenario: Scenario,
    cache_key: str | None = None,
    client_data_version: str | None = None,
) -> dict[str, object]:
    from calculations.domain.services.scenario_effects_cache import (
        get_compact_status,
        get_scenario_effects_revision,
    )
    from calculations.domain.services.scenario_warm_status import get_warm_status

    readiness = _build_cache_readiness_payload(scenario=scenario)
    warm_status = get_warm_status(scenario_id=scenario.id)

    data_version = get_scenario_effects_revision(scenario_id=scenario.id)
    compact_ready = bool(readiness.get("compact_ready"))
    early_group_ready = False
    fallout_ready = False

    if cache_key:
        compact_status = get_compact_status(cache_key=cache_key)
        compact_ready = bool(compact_status.get("compact_ready"))
        early_group_ready = bool(compact_status.get("early_group_ready"))
        fallout_ready = bool(compact_status.get("fallout_ready"))
        status_data_version = compact_status.get("data_version")
        if isinstance(status_data_version, str):
            data_version = status_data_version

    data_version_changed = bool(
        client_data_version
        and data_version
        and client_data_version != data_version,
    )

    mart_phase = readiness.get("mart_phase")
    scenario_phase = readiness.get("scenario_phase")
    mart_ready = bool(readiness.get("mart_ready"))
    kpi_ready = bool(readiness.get("kpi_ready"))
    ready_for_compute = bool(readiness.get("ready_for_compute"))
    message = str(readiness.get("message") or "Обновление данных…")

    rebuild_message = None
    error = None
    if warm_status:
        rebuild_message = warm_status.get("rebuild_message")
        if mart_phase == "error" or scenario_phase == "error":
            error = warm_status.get("error")

    elasticity_enabled = bool(scenario.consider_demand_elasticity)
    stage = _resolve_stage(
        mart_phase=mart_phase,
        scenario_phase=scenario_phase,
        mart_ready=mart_ready,
        kpi_ready=kpi_ready,
        ready_for_compute=ready_for_compute,
        cache_key=cache_key,
        compact_ready=compact_ready,
        fallout_ready=fallout_ready,
        elasticity_enabled=elasticity_enabled,
    )
    message = _stage_message(
        stage=stage,
        default_message=message,
        mart_phase=mart_phase,
        scenario_phase=scenario_phase,
        error=error if isinstance(error, str) else None,
    )

    return {
        "stage": stage,
        "message": message,
        "data_version": data_version,
        "data_version_changed": data_version_changed,
        "mart_phase": mart_phase,
        "mart_ready": mart_ready,
        "scenario_phase": scenario_phase,
        "ready_for_compute": ready_for_compute,
        "kpi_ready": kpi_ready,
        "compact_ready": compact_ready,
        "early_group_ready": early_group_ready,
        "fallout_ready": fallout_ready,
        "rebuild_message": rebuild_message,
        "error": error,
    }


def _resolve_stage(
    *,
    mart_phase: object,
    scenario_phase: object,
    mart_ready: bool,
    kpi_ready: bool,
    ready_for_compute: bool,
    cache_key: str | None,
    compact_ready: bool,
    fallout_ready: bool,
    elasticity_enabled: bool,
) -> DecisionEffectsStage:
    if mart_phase == "error" or scenario_phase == "error":
        return "error"

    if not mart_ready and mart_phase in {"queued", "building"}:
        return "mart_rebuilding"

    if scenario_phase in {"mask", "kpi", "compact"} and not kpi_ready:
        return "scenario_warming"

    if cache_key:
        if not compact_ready:
            return "compact_pending"
        if elasticity_enabled and not fallout_ready:
            return "fallout_pending"
        return "done"

    if ready_for_compute:
        return "ready_for_compute"

    if scenario_phase in {"mask", "kpi", "compact", "queued"}:
        return "scenario_warming"

    return "ready_for_compute"


def _stage_message(
    *,
    stage: DecisionEffectsStage,
    default_message: str,
    mart_phase: object,
    scenario_phase: object,
    error: str | None,
) -> str:
    if stage == "error":
        return error or default_message
    if stage == "mart_rebuilding":
        return "Пересборка витрины маршрутов…"
    if stage == "scenario_warming":
        if scenario_phase == "mask":
            return "Пересборка масок сценария…"
        if scenario_phase == "kpi":
            return "Обновление итогов сценария…"
        if scenario_phase == "compact":
            return "Детализация в фоне…"
        return default_message
    if stage == "compact_pending":
        return "Детализация в фоне…"
    if stage == "fallout_pending":
        return "Расчёт эластичности…"
    if stage == "done":
        return "Пересчёт завершён"
    return default_message
