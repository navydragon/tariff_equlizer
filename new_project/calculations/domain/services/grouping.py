from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from decimal import Decimal
from typing import TypeVar

from calculations.domain.services.scenario_effects_cache import RouteEffectFact

T = TypeVar("T")


def fact_dimension_value(fact: RouteEffectFact, dimension: str) -> str:
    if dimension == "cargo_group":
        return fact.cargo_group
    if dimension == "cargo_code":
        return fact.cargo_code
    if dimension == "direction":
        return fact.direction
    if dimension == "wagon_kind":
        return fact.wagon_kind
    if dimension == "transport_type":
        return fact.transport_type
    if dimension == "shipment_category":
        return fact.shipment_category
    if dimension == "park_type":
        return fact.park_type
    if dimension == "holding":
        return fact.holding
    return "—"


def build_group_keys(
    fact: RouteEffectFact,
    *,
    group_by: str,
    group_by_inner: str,
) -> list[tuple[str, ...]]:
    outer = fact_dimension_value(fact, group_by)
    if group_by_inner == "none":
        return [(outer,)]
    inner = fact_dimension_value(fact, group_by_inner)
    return [(outer, inner), (outer, "ИТОГО")]


def aggregate_by_groups(
    facts: list[RouteEffectFact],
    *,
    group_by: str,
    group_by_inner: str,
    value_fn: Callable[[RouteEffectFact], Decimal],
    cargo_filter: set[str] | None = None,
    holding_filter: set[str] | None = None,
) -> dict[tuple[str, ...], Decimal]:
    buckets: dict[tuple[str, ...], Decimal] = defaultdict(Decimal)

    for fact in facts:
        if cargo_filter is not None and fact.cargo_group not in cargo_filter:
            continue
        if holding_filter is not None and fact.holding not in holding_filter:
            continue

        value = value_fn(fact)
        for key in build_group_keys(
            fact,
            group_by=group_by,
            group_by_inner=group_by_inner,
        ):
            buckets[key] += value

    return buckets


def grand_total_key_sum(
    buckets: dict[tuple[str, ...], Decimal],
    *,
    group_by_inner: str,
) -> Decimal:
    if group_by_inner == "none":
        return sum(
            (value for key, value in buckets.items() if len(key) == 1),
            Decimal("0"),
        )
    return sum(
        (
            value
            for key, value in buckets.items()
            if len(key) == 2 and key[1] == "ИТОГО"
        ),
        Decimal("0"),
    )
