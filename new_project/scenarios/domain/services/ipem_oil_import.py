"""Импорт model-маршрутов нефти и правил эластичности из IPEM XLSX."""
from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from core.management.ipem_economics import import_ipem_oil_model_routes
from core.models import Route, RouteSet
from scenarios.domain.services.ipem_oil_elasticity_seed import (
    IpemOilElasticitySeedResult,
    seed_ipem_oil_elasticity_for_scenario,
)
from scenarios.domain.utils.elasticity_matching import select_rule_for_route
from scenarios.models import ElasticityRule, Scenario


@dataclass
class ElasticityMatchingStats:
    matched: int = 0
    unmatched_route_codes: list[str] = field(default_factory=list)


@dataclass
class IpemOilBundleResult:
    seed: IpemOilElasticitySeedResult | None
    routes: object
    matching: ElasticityMatchingStats


def validate_model_route_elasticity_matching(
    route_set: RouteSet,
    scenario: Scenario,
) -> ElasticityMatchingStats:
    stats = ElasticityMatchingStats()
    if not scenario.elasticity_set_id:
        return stats

    rules = list(
        ElasticityRule.objects.filter(
            elasticity_set_id=scenario.elasticity_set_id,
        ).select_related("cargo_group", "cargo", "message_type"),
    )
    model_routes = Route.objects.filter(
        route_set=route_set,
        is_model=True,
    ).select_related("cargo", "cargo__cargo_group", "message_type")

    for route in model_routes:
        rule = select_rule_for_route(route, rules)
        if rule is None:
            stats.unmatched_route_codes.append(route.route_code)
        else:
            stats.matched += 1

    return stats


def import_ipem_oil_bundle(
    scenario: Scenario,
    xlsx_path: Path,
    route_set: RouteSet,
    *,
    dry_run: bool = False,
    attach_elasticity: bool = True,
    progress: Callable[[str], None] | None = None,
) -> IpemOilBundleResult:
    seed_result: IpemOilElasticitySeedResult | None = None
    if attach_elasticity:
        seed_result = seed_ipem_oil_elasticity_for_scenario(
            scenario,
            author=scenario.author,
            attach=True,
            xlsx_path=xlsx_path,
        )
        scenario.refresh_from_db(fields=["elasticity_set_id"])

    routes_result = import_ipem_oil_model_routes(
        xlsx_path,
        route_set,
        dry_run=dry_run,
        progress=progress,
    )

    matching = ElasticityMatchingStats()
    if not dry_run and attach_elasticity and scenario.elasticity_set_id:
        matching = validate_model_route_elasticity_matching(
            route_set,
            scenario,
        )

    return IpemOilBundleResult(
        seed=seed_result,
        routes=routes_result,
        matching=matching,
    )
