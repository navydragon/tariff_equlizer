from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db.models import QuerySet

from core.models import Route, RouteSet


@dataclass(frozen=True)
class ModelRouteEconomicsRow:
    route_id: int
    cargo_id: int | None
    cargo_group_id: int | None
    message_type_id: int | None
    holding: str
    direction: str
    transport_volume_tons: Decimal
    market_price_per_ton: Decimal | None
    production_cost_per_ton: Decimal | None
    total_cost_per_ton: Decimal | None
    rzd_cost_total_per_ton: Decimal | None
    operators_cost_per_ton: Decimal | None
    transshipment_cost_per_ton: Decimal | None
    enterprise_load_coefficient: Decimal | None


class OperationalElasticityRepository:
    def list_model_routes(self, route_set_id: int) -> list[ModelRouteEconomicsRow]:
        qs = (
            Route.objects.model_routes()
            .filter(route_set_id=route_set_id)
            .select_related(
                "cargo",
                "cargo__cargo_group",
                "message_type",
                "shipper",
                "origin_station__railroad",
            )
        )
        return [self._to_row(route) for route in qs]

    def operational_queryset(self, route_set_id: int) -> QuerySet[Route]:
        return (
            Route.objects.operational()
            .filter(route_set_id=route_set_id)
            .select_related(
                "cargo",
                "cargo__cargo_group",
                "message_type",
                "shipper",
                "origin_station__railroad",
                "model_route",
            )
        )

    @staticmethod
    def _holding(route: Route) -> str:
        if route.shipper_id and route.shipper.holding:
            holding = route.shipper.holding.strip()
            if holding:
                return holding
        return "Прочие"

    @staticmethod
    def _direction(route: Route) -> str:
        if not route.origin_station_id:
            return "—"
        railroad = route.origin_station.railroad
        if railroad is None:
            return "—"
        direction = (railroad.direction or "").strip()
        return direction or "—"

    def _to_row(self, route: Route) -> ModelRouteEconomicsRow:
        cargo_group_id = (
            route.cargo.cargo_group_id if route.cargo_id else None
        )
        return ModelRouteEconomicsRow(
            route_id=route.id,
            cargo_id=route.cargo_id,
            cargo_group_id=cargo_group_id,
            message_type_id=route.message_type_id,
            holding=self._holding(route),
            direction=self._direction(route),
            transport_volume_tons=route.transport_volume_tons or Decimal("0"),
            market_price_per_ton=route.market_price_per_ton,
            production_cost_per_ton=route.production_cost_per_ton,
            total_cost_per_ton=route.total_cost_per_ton,
            rzd_cost_total_per_ton=route.rzd_cost_total_per_ton,
            operators_cost_per_ton=route.operators_cost_per_ton,
            transshipment_cost_per_ton=route.transshipment_cost_per_ton,
            enterprise_load_coefficient=route.enterprise_load_coefficient,
        )

    def reset_operational_elasticity_flags(self, route_set: RouteSet) -> int:
        return (
            Route.objects.operational()
            .filter(route_set=route_set)
            .exclude(
                skip_elasticity=True,
                elasticity_source=Route.ElasticitySource.NONE,
            )
            .update(
                skip_elasticity=True,
                elasticity_source=Route.ElasticitySource.NONE,
            )
        )
