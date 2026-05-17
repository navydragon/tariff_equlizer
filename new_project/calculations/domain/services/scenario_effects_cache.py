from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from decimal import Decimal

import numpy as np
from django.core.cache import cache

CACHE_PREFIX = "scenario_effects"
CACHE_TIMEOUT_SECONDS = 60 * 60


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
