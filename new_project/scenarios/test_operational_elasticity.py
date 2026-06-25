from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)
from scenarios.domain.services.operational_elasticity import (
    assign_operational_elasticity_sources,
)
from scenarios.models import Scenario


class OperationalElasticityAssignmentTests(TestCase):
    def setUp(self) -> None:
        user_model = get_user_model()
        self.user = user_model.objects.create_user(
            login="elasticity_assign",
            password="pass",
        )
        self.route_set = RouteSet.objects.create(
            name="Elasticity RS",
            code="ELASTICITY_RS",
        )
        self.scenario = Scenario.objects.create(
            name="Elasticity scenario",
            route_set=self.route_set,
            author=self.user,
            start_year=2025,
            end_year=2027,
        )
        self.cargo_group = CargoGroup.objects.create(code=10, name="Уголь", position=1)
        self.cargo = Cargo.objects.create(
            code="101010",
            name="Уголь каменный",
            cargo_group=self.cargo_group,
        )
        self.wagon = WagonKind.objects.create(name="Полувагон")
        self.shipment = ShipmentType.objects.create(name="Повагонная")
        self.message_type = MessageType.objects.create(name="Внутренний рынок")
        railroad = RailRoad.objects.create(
            code="01",
            name="Октябрьская",
            direction="Северо-Запад",
        )
        region = Region.objects.create(
            full_name="Elasticity region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=100001,
            short_name="STA",
            full_name="Станция А",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=200002,
            short_name="STB",
            full_name="Станция Б",
            region=region,
            railroad=railroad,
        )

    def _create_operational(self, *, route_code: str) -> Route:
        return Route.objects.create(
            route_set=self.route_set,
            route_code=route_code,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon,
            shipment_type=self.shipment,
            message_type=self.message_type,
            freight_charge_rub=Decimal("1000000"),
            transport_volume_tons=Decimal("50000"),
            market_price_per_ton=Decimal("2000"),
            production_cost_per_ton=Decimal("500"),
            rzd_cost_total_per_ton=Decimal("1000"),
        )

    def _create_model(self, *, route_code: str, volume: str = "10000") -> Route:
        return Route.objects.create(
            route_set=self.route_set,
            route_code=route_code,
            is_model=True,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon,
            shipment_type=self.shipment,
            message_type=self.message_type,
            transport_volume_tons=Decimal(volume),
            market_price_per_ton=Decimal("2000"),
            production_cost_per_ton=Decimal("500"),
            rzd_cost_total_per_ton=Decimal("1000"),
            enterprise_load_coefficient=Decimal("0.8000"),
        )

    def test_assign_direct_model_link(self) -> None:
        model_route = self._create_model(route_code="IPEM-1")
        operational = self._create_operational(route_code="OP-1")
        operational.model_route = model_route
        operational.save(update_fields=["model_route"])

        stats = assign_operational_elasticity_sources(self.route_set)
        operational.refresh_from_db()

        self.assertEqual(stats.direct_model, 1)
        self.assertFalse(operational.skip_elasticity)
        self.assertEqual(
            operational.elasticity_source,
            Route.ElasticitySource.DIRECT_MODEL,
        )

    def test_assign_holding_aggregate_when_no_direct_link(self) -> None:
        self._create_model(route_code="IPEM-AGG")
        operational = self._create_operational(route_code="OP-AGG")

        stats = assign_operational_elasticity_sources(self.route_set)
        operational.refresh_from_db()

        self.assertEqual(stats.holding_aggregate, 1)
        self.assertFalse(operational.skip_elasticity)
        self.assertEqual(
            operational.elasticity_source,
            Route.ElasticitySource.HOLDING_AGGREGATE,
        )

    def test_skip_when_no_model_pool(self) -> None:
        operational = self._create_operational(route_code="OP-SKIP")

        stats = assign_operational_elasticity_sources(self.route_set)
        operational.refresh_from_db()

        self.assertEqual(stats.skipped, 1)
        self.assertTrue(operational.skip_elasticity)
        self.assertEqual(operational.elasticity_source, Route.ElasticitySource.NONE)

    def test_assign_cargo_group_aggregate_when_holding_group_missing(self) -> None:
        other_group = CargoGroup.objects.create(code=20, name="Руда", position=2)
        other_cargo = Cargo.objects.create(
            code="202020",
            name="Руда железная",
            cargo_group=other_group,
        )
        model_shipper = Shipper.objects.create(
            name="Model shipper",
            holding="Холдинг model",
        )
        operational_shipper = Shipper.objects.create(
            name="Operational shipper",
            holding="Холдинг operational",
        )
        model_route = self._create_model(route_code="IPEM-CG", volume="10000")
        Route.objects.filter(pk=model_route.pk).update(
            cargo=other_cargo,
            shipper=model_shipper,
        )
        operational = self._create_operational(route_code="OP-CG")
        Route.objects.filter(pk=operational.pk).update(
            cargo=other_cargo,
            shipper=operational_shipper,
        )

        stats = assign_operational_elasticity_sources(self.route_set)
        operational.refresh_from_db()

        self.assertEqual(stats.holding_aggregate, 0)
        self.assertEqual(stats.cargo_group_aggregate, 1)
        self.assertEqual(
            operational.elasticity_source,
            Route.ElasticitySource.CARGO_GROUP_AGGREGATE,
        )

    def test_direct_model_has_priority_over_aggregate(self) -> None:
        self._create_model(route_code="IPEM-PRIORITY")
        model_route = Route.objects.get(route_code="IPEM-PRIORITY")
        operational = self._create_operational(route_code="OP-PRIORITY")
        operational.model_route = model_route
        operational.save(update_fields=["model_route"])

        stats = assign_operational_elasticity_sources(self.route_set)
        operational.refresh_from_db()

        self.assertEqual(stats.direct_model, 1)
        self.assertEqual(stats.holding_aggregate, 0)
        self.assertEqual(
            operational.elasticity_source,
            Route.ElasticitySource.DIRECT_MODEL,
        )
