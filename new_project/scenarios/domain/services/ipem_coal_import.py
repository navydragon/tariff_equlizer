"""Объединённый импорт угольных model-маршрутов и правил эластичности из IPEM XLSX."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path

from core.management.ipem_economics import (
    IpemCoal2026ImportResult,
    import_ipem_coal_2026_model_routes,
)
from core.models import Route, RouteSet
from scenarios.domain.repositories.elasticity import ElasticityRuleRepository
from scenarios.domain.services.base_elasticity_seed import (
    EXPORT_RULE_NAME,
    INTERNAL_RULE_NAME,
    ElasticitySeedResult,
    seed_coal_elasticity_for_scenario,
)
from scenarios.domain.utils.elasticity_matching import select_rule_for_route
from scenarios.models import ElasticityRule, Scenario


@dataclass
class ElasticityMatchingStats:
    export_matched: int = 0
    internal_matched: int = 0
    unmatched_route_codes: list[str] = field(default_factory=list)


@dataclass
class IpemCoal2026BundleResult:
    seed: ElasticitySeedResult | None
    routes: IpemCoal2026ImportResult
    matching: ElasticityMatchingStats


def resolve_elasticity_rules_for_scenario(scenario: Scenario) -> list[ElasticityRule]:
    if not scenario.elasticity_set_id:
        return []
    return ElasticityRuleRepository().list_by_set(scenario.elasticity_set_id)


def resolve_elasticity_rule_for_route(
    route: Route,
    scenario: Scenario,
) -> ElasticityRule | None:
    rules = resolve_elasticity_rules_for_scenario(scenario)
    return select_rule_for_route(route, rules)


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
        elif rule.name == EXPORT_RULE_NAME:
            stats.export_matched += 1
        elif rule.name == INTERNAL_RULE_NAME:
            stats.internal_matched += 1

    return stats


def import_ipem_coal_2026_bundle(
    scenario: Scenario,
    xlsx_path: Path,
    route_set: RouteSet,
    *,
    dry_run: bool = False,
    attach_elasticity: bool = True,
) -> IpemCoal2026BundleResult:
    seed_result: ElasticitySeedResult | None = None
    if attach_elasticity:
        seed_result = seed_coal_elasticity_for_scenario(
            scenario,
            author=scenario.author,
            attach=True,
            xlsx_path=xlsx_path,
        )
        scenario.refresh_from_db(fields=["elasticity_set_id"])

    routes_result = import_ipem_coal_2026_model_routes(
        xlsx_path,
        route_set,
        dry_run=dry_run,
    )

    matching = ElasticityMatchingStats()
    if not dry_run and attach_elasticity and scenario.elasticity_set_id:
        matching = validate_model_route_elasticity_matching(route_set, scenario)

    return IpemCoal2026BundleResult(
        seed=seed_result,
        routes=routes_result,
        matching=matching,
    )
