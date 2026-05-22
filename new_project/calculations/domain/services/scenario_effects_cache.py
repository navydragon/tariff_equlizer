from __future__ import annotations

import hashlib
import json
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


@dataclass
class CompactRouteEffects:
    years: list[int]
    dimensions: dict[str, np.ndarray]
    dimension_labels: dict[str, list[str]]
    baseline_ths: np.ndarray
    volume_mln_tons: np.ndarray
    base_by_year: np.ndarray
    rules_by_year: np.ndarray
    charge_by_year: np.ndarray
    rule_meta: list[tuple[int, str]] = field(default_factory=list)
    rule_by_year: np.ndarray | None = None


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
    baseline_ths: Decimal
    volume_mln_tons: Decimal = Decimal("0")
    base_by_year: dict[int, Decimal] = field(default_factory=dict)
    rules_by_year: dict[int, Decimal] = field(default_factory=dict)
    charge_by_year: dict[int, Decimal] = field(default_factory=dict)
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
    ]
    for year in sorted(base_coef_by_year):
        parts.append(f"base:{year}:{base_coef_by_year[year]}")
    for rule in rules:
        parts.append(
            f"rule:{rule.id}:{rule.position}:{rule.base_percent}",
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


def store_payload(*, cache_key: str, payload: ScenarioEffectsCachePayload) -> None:
    cache.set(cache_key, payload, CACHE_TIMEOUT_SECONDS)


def get_payload(cache_key: str) -> ScenarioEffectsCachePayload | None:
    payload = cache.get(cache_key)
    if isinstance(payload, ScenarioEffectsCachePayload):
        return payload
    return None


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
