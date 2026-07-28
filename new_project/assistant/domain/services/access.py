from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from core.domain.services.app_settings import AppSettingsService
from core.models import Route
from scenarios.models import Scenario


@dataclass(frozen=True)
class RouteAnalysisContext:
    scenario: Scenario
    route: Route


class AssistantAccessHelper:
    """ACL для контекста «Экономика грузов» (как в route_analysis_api)."""

    def __init__(self, app_settings: AppSettingsService | None = None) -> None:
        self._settings = app_settings or AppSettingsService()

    def require_route_analysis_context(
        self,
        *,
        scenario_id: int,
        route_id: int,
        user: Any | None = None,
    ) -> tuple[RouteAnalysisContext | None, list[str]]:
        try:
            scenario = (
                Scenario.objects.select_related(
                    "inflation_set",
                    "exchange_rate_set",
                    "route_set",
                )
                .prefetch_related(
                    "inflation_set__values",
                    "exchange_rate_set__values",
                    "price_change_settings",
                )
                .get(pk=scenario_id)
            )
        except Scenario.DoesNotExist:
            return None, ["Сценарий не найден"]

        if user is not None:
            if not self._settings.can_read_scenario(
                author_id=scenario.author_id,
                user_id=user.id,
            ):
                return None, ["Сценарий не найден"]

        try:
            route = Route.objects.select_related(
                "cargo",
                "cargo__cargo_group",
                "shipper",
                "message_type",
                "origin_station",
                "destination_station",
                "model_route",
            ).get(pk=route_id)
        except Route.DoesNotExist:
            return None, ["Маршрут не найден"]

        if route.route_set_id != scenario.route_set_id:
            return None, ["Маршрут не найден"]

        return RouteAnalysisContext(scenario=scenario, route=route), []
