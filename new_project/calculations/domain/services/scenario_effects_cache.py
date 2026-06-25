from __future__ import annotations

import hashlib
import json
import time
import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
from django.core.cache import cache

from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from scenarios.models import Scenario, TariffRule

CACHE_PREFIX = "scenario_effects"
STABLE_CACHE_PREFIX = f"{CACHE_PREFIX}:stable"
CACHE_TIMEOUT_SECONDS = 60 * 60 * 24
COMPACT_WAIT_TIMEOUT_SECONDS = 60.0
COMPACT_API_WAIT_TIMEOUT_SECONDS = 3.0
COMPACT_WAIT_POLL_INTERVAL_SECONDS = 0.05


@dataclass
class CompactRouteEffects:
    years: list[int]
    dimensions: dict[str, np.ndarray]
    dimension_labels: dict[str, list[str]]
    baseline_rub: np.ndarray
    volume_tons: np.ndarray
    base_by_year: np.ndarray
    rules_by_year: np.ndarray
    charge_by_year: np.ndarray
    rule_meta: list[tuple[int, str]] = field(default_factory=list)
    rule_by_year: np.ndarray | None = None
    volume_by_year: np.ndarray | None = None
    volume_fallout_by_year: np.ndarray | None = None
    money_fallout_by_year: np.ndarray | None = None
    route_ids: np.ndarray | None = None


@dataclass
class RouteEffectFact:
    cargo_group: str
    cargo_code: str
    direction: str
    wagon_kind: str
    transport_type: str
    shipment_category: str
    park_type: str
    holding: str
    baseline_rub: Decimal
    volume_tons: Decimal = Decimal("0")
    base_by_year: dict[int, Decimal] = field(default_factory=dict)
    rules_by_year: dict[int, Decimal] = field(default_factory=dict)
    charge_by_year: dict[int, Decimal] = field(default_factory=dict)
    volume_fallout_by_year: dict[int, Decimal] = field(default_factory=dict)
    money_fallout_by_year: dict[int, Decimal] = field(default_factory=dict)
    rule_by_year: dict[int, dict[int, Decimal]] = field(default_factory=dict)


@dataclass
class ScenarioEffectsCachePayload:
    user_id: int
    scenario_id: int
    years: list[int]
    routes_without_charge: int
    routes_without_volume: int
    baseline_total: Decimal
    facts: list[RouteEffectFact] = field(default_factory=list)
    compact: CompactRouteEffects | None = None
    compact_pending: bool = False
    data_version: str | None = None


@dataclass
class ScenarioComputeSnapshot:
    """Результат compute для сценария (без привязки к пользователю)."""

    data_version: str
    years: list[int]
    routes_without_charge: int
    routes_without_volume: int
    global_totals: GlobalTotals
    compact: CompactRouteEffects | None
    filter_options: dict[str, list[str]]


def compute_scenario_data_version(
    *,
    scenario: Scenario,
    base_coef_by_year: dict[int, Decimal],
    rules: list[TariffRule],
) -> str:
    """
    Версия входных данных для инвалидации стабильного кэша:
    набор маршрутов + коэффициенты + тарифные правила.
    """
    route_set = scenario.route_set
    parts: list[str] = [
        str(scenario.id),
        str(scenario.start_year),
        str(scenario.end_year),
        str(route_set.id),
        route_set.updated_at.isoformat() if route_set.updated_at else "",
        f"consider_turnover_changes:{bool(getattr(scenario, 'consider_turnover_changes', False))}",
        f"consider_demand_elasticity:{bool(getattr(scenario, 'consider_demand_elasticity', False))}",
        f"elasticity_set:{getattr(scenario, 'elasticity_set_id', None)}",
        f"retention_mode:{getattr(scenario, 'retention_coefficient_mode', '')}",
    ]
    for year in sorted(base_coef_by_year):
        parts.append(f"base:{year}:{base_coef_by_year[year]}")
    for rule in rules:
        parts.append(
            f"rule:{rule.id}:{rule.name}:{rule.position}:{rule.base_percent}",
        )
        for condition in rule.conditions.all():
            parts.append(
                json.dumps(
                    {
                        "parameter": condition.parameter,
                        "operator": condition.operator,
                        "values": condition.values,
                    },
                    sort_keys=True,
                    ensure_ascii=False,
                ),
            )
        for year_value in rule.year_values.all():
            parts.append(f"coef:{year_value.year}:{year_value.coefficient}")
    digest = hashlib.sha256("\n".join(parts).encode("utf-8")).hexdigest()
    return digest[:16]


def stable_snapshot_cache_key(*, scenario_id: int, data_version: str) -> str:
    return f"{STABLE_CACHE_PREFIX}:{scenario_id}:{data_version}"


def get_scenario_snapshot(
    *,
    scenario_id: int,
    data_version: str,
) -> ScenarioComputeSnapshot | None:
    payload = cache.get(
        stable_snapshot_cache_key(scenario_id=scenario_id, data_version=data_version),
    )
    if isinstance(payload, ScenarioComputeSnapshot):
        return payload
    return None


def store_scenario_snapshot(
    *,
    scenario_id: int,
    snapshot: ScenarioComputeSnapshot,
) -> None:
    cache.set(
        stable_snapshot_cache_key(
            scenario_id=scenario_id,
            data_version=snapshot.data_version,
        ),
        snapshot,
        CACHE_TIMEOUT_SECONDS,
    )


def make_cache_key(*, user_id: int, scenario_id: int) -> str:
    token = uuid.uuid4().hex
    return f"{CACHE_PREFIX}:{user_id}:{scenario_id}:{token}"


def _payload_for_redis(payload: ScenarioEffectsCachePayload) -> ScenarioEffectsCachePayload:
    """Compact хранится только на диске (.npy-массивы); в Redis — метаданные сессии."""
    if payload.compact is None:
        return payload
    return ScenarioEffectsCachePayload(
        user_id=payload.user_id,
        scenario_id=payload.scenario_id,
        years=payload.years,
        routes_without_charge=payload.routes_without_charge,
        routes_without_volume=payload.routes_without_volume,
        baseline_total=payload.baseline_total,
        facts=payload.facts,
        compact=None,
        compact_pending=payload.compact_pending,
        data_version=payload.data_version,
    )


def store_payload(*, cache_key: str, payload: ScenarioEffectsCachePayload) -> None:
    cache.set(cache_key, _payload_for_redis(payload), CACHE_TIMEOUT_SECONDS)


def _hydrate_payload_from_disk(
    payload: ScenarioEffectsCachePayload,
) -> ScenarioEffectsCachePayload:
    if payload.compact is not None or not payload.data_version:
        return payload

    from calculations.domain.services.scenario_compute_store import (
        try_load_scenario_compute,
    )

    bundle = try_load_scenario_compute(
        scenario_id=payload.scenario_id,
        data_version=payload.data_version,
    )
    if bundle is None:
        return payload

    compact = bundle.compact
    compact_pending = payload.compact_pending
    if compact is not None:
        if compact.rule_meta and compact.rule_by_year is None:
            compact_pending = True
        else:
            compact_pending = False

    return ScenarioEffectsCachePayload(
        user_id=payload.user_id,
        scenario_id=payload.scenario_id,
        years=payload.years,
        routes_without_charge=payload.routes_without_charge,
        routes_without_volume=payload.routes_without_volume,
        baseline_total=payload.baseline_total,
        facts=payload.facts,
        compact=compact,
        compact_pending=compact_pending,
        data_version=payload.data_version,
    )


def get_payload(cache_key: str) -> ScenarioEffectsCachePayload | None:
    payload = cache.get(cache_key)
    if not isinstance(payload, ScenarioEffectsCachePayload):
        return None
    return _hydrate_payload_from_disk(payload)


def get_payload_ready(
    cache_key: str,
    *,
    timeout_seconds: float = COMPACT_WAIT_TIMEOUT_SECONDS,
) -> ScenarioEffectsCachePayload | None:
    """Возвращает payload с compact; ждёт фоновую сборку при compact_pending."""
    deadline = time.perf_counter() + timeout_seconds
    while True:
        payload = get_payload(cache_key)
        if payload is None:
            return None
        if payload.compact is not None or not payload.compact_pending:
            return payload
        if time.perf_counter() >= deadline:
            return payload
        time.sleep(COMPACT_WAIT_POLL_INTERVAL_SECONDS)


def update_payload_compact(
    *,
    cache_key: str,
    compact: CompactRouteEffects,
) -> None:
    del compact
    payload = cache.get(cache_key)
    if not isinstance(payload, ScenarioEffectsCachePayload):
        return
    payload.compact = None
    payload.compact_pending = False
    cache.set(cache_key, _payload_for_redis(payload), CACHE_TIMEOUT_SECONDS)


def validate_cache_access(
    *,
    payload: ScenarioEffectsCachePayload,
    user_id: int,
    scenario_id: int,
) -> list[str]:
    if payload.user_id != user_id:
        return ["Кэш расчёта недоступен"]
    if payload.scenario_id != scenario_id:
        return ["Кэш расчёта не соответствует сценарию"]
    return []


REVISION_PREFIX = f"{CACHE_PREFIX}:rev"


def revision_cache_key(*, scenario_id: int) -> str:
    return f"{REVISION_PREFIX}:{scenario_id}"


def set_scenario_effects_revision(*, scenario_id: int, data_version: str) -> None:
    cache.set(
        revision_cache_key(scenario_id=scenario_id),
        data_version,
        CACHE_TIMEOUT_SECONDS,
    )


def get_scenario_effects_revision(*, scenario_id: int) -> str | None:
    value = cache.get(revision_cache_key(scenario_id=scenario_id))
    return value if isinstance(value, str) else None


def get_compact_status(*, cache_key: str) -> dict[str, object]:
    payload = cache.get(cache_key)
    if not isinstance(payload, ScenarioEffectsCachePayload):
        return {"compact_ready": False, "data_version": None}

    data_version = payload.data_version
    if payload.compact_pending and data_version:
        from calculations.domain.services.scenario_compute_store import (
            is_scenario_compact_on_disk,
        )

        if is_scenario_compact_on_disk(
            scenario_id=payload.scenario_id,
            data_version=data_version,
        ):
            return {"compact_ready": True, "data_version": data_version}

    compact_ready = not payload.compact_pending
    return {
        "compact_ready": compact_ready,
        "data_version": data_version,
    }
