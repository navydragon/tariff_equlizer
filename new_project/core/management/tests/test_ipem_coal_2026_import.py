from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.management.ipem_economics import (
    IpemCoal2026ResolvedRow,
    build_model_route_from_resolved_row,
    clear_ipem_model_routes,
    link_operational_routes_to_models,
)
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    ShipmentType,
    Station,
    WagonKind,
)


class IpemCoal2026ImportTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(code="RZD_2026_IMPORT", name="RZD import")
        cargo_group = CargoGroup.objects.create(name="Уголь", code=1, position=1)
        self.cargo = Cargo.objects.create(
            code="016111",
            name="УГОЛЬ Г",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="96", name="ДВС")
        region = Region.objects.create(
            short_name="R",
            full_name="Region",
            type="край",
        )
        self.origin = Station.objects.create(
            esr_code=91720,
            short_name="ЧЕГДОМЫН",
            full_name="ЧЕГДОМЫН",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=96780,
            short_name="ВАНИНО-ЭКСП",
            full_name="ВАНИНО-ЭКСП",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_PV", name="Полувагоны")
        self.shipment_type = ShipmentType.objects.create(
            code="ST_M",
            name="маршрутная",
        )
        self.message_type = MessageType.objects.create(code="MT_EXP", name="Экспорт")

        for idx in (1, 2):
            Route.objects.create(
                route_set=self.route_set,
                cargo=self.cargo,
                origin_station=self.origin,
                destination_station=self.destination,
                wagon_kind=self.wagon_kind,
                shipment_type=self.shipment_type,
                message_type=self.message_type,
                route_code=f"OP-{idx}",
                freight_charge_rub=Decimal("1000.00"),
            )

    def test_model_route_constraint(self) -> None:
        model_route = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-1",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )
        with self.assertRaises(Exception):
            Route.objects.create(
                route_set=self.route_set,
                is_model=True,
                model_route=model_route,
                route_code="MODEL-2",
                cargo=self.cargo,
                origin_station=self.origin,
                destination_station=self.destination,
                wagon_kind=self.wagon_kind,
                shipment_type=self.shipment_type,
                message_type=self.message_type,
            )

    def test_link_operational_routes_to_models(self) -> None:
        model_route = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-LINK",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            market_price_per_ton=Decimal("5000.00"),
        )
        linked = link_operational_routes_to_models(self.route_set, [model_route])
        self.assertEqual(linked, 2)
        self.assertEqual(
            Route.objects.operational()
            .filter(model_route=model_route)
            .count(),
            2,
        )

    def test_import_creates_model_route_from_resolved_row(self) -> None:
        resolved = IpemCoal2026ResolvedRow(
            ipem_row=1,
            route_code="IPEM2026-001",
            origin=self.origin,
            destination=self.destination,
            cargo=self.cargo,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            shipper=None,
            economics={"market_price_per_ton": Decimal("5000.00")},
            transport_volume_tons=Decimal("1000.00"),
            freight_turnover_tkm=Decimal("500000.00"),
            freight_charge_rub=Decimal("100000.00"),
            distance_belt_midpoint_km=500,
            load_tons_per_wagon=Decimal("70.00"),
            delivery_time_loaded_days=5,
            delivery_time_empty_days=5,
            delivery_time_ops_days=1,
            rate_per_wagon_per_day=Decimal("1500.00"),
        )
        clear_ipem_model_routes(self.route_set)
        model_route = build_model_route_from_resolved_row(self.route_set, resolved)
        model_route.save()

        self.assertTrue(model_route.is_model)
        self.assertIsNone(model_route.model_route_id)
        self.assertEqual(model_route.market_price_per_ton, Decimal("5000.00"))
        linked = link_operational_routes_to_models(self.route_set, [model_route])
        self.assertEqual(linked, 2)

    def test_import_command_dry_run(self) -> None:
        xlsx_path = (
            Path(__file__).resolve().parents[4]
            / "data"
            / "ipem"
            / "Уголь_эластика_2026.xlsx"
        )
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        call_command(
            "import_ipem_coal_2026_routes",
            "--file",
            str(xlsx_path),
            "--route-set-code",
            "RZD_2026_IMPORT",
            "--dry-run",
        )
        self.assertEqual(
            Route.objects.filter(route_set=self.route_set, is_model=True).count(),
            0,
        )

    def test_model_routes_excluded_from_route_set_stats(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_route_set_stats,
        )

        Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-STATS",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            freight_charge_rub=Decimal("999999.00"),
        )
        skipped_charge, _without_volume = fetch_route_set_stats(self.route_set.pk)
        self.assertEqual(skipped_charge, 0)
