from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.management.ipem_economics import (
    IpemCoal2026ResolvedRow,
    build_model_route_from_resolved_row,
    clear_ipem_model_routes_for_cargo_groups,
    link_operational_routes_to_models,
    load_ipem_forest_xlsx,
    parse_ipem_coal_2026_economics_row,
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


def _forest_xlsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "data"
        / "ipem"
        / "Лес_эластика.xlsx"
    )


class IpemForestImportTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(
            code="RZD_2026_FOREST",
            name="RZD forest import",
        )
        cargo_group = CargoGroup.objects.create(
            name="Лесные грузы",
            code=6,
            position=6,
        )
        self.cargo = Cargo.objects.create(
            code="09111",
            name="ПИЛМАТ ПР",
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
        self.wagon_kind = WagonKind.objects.create(code="WK_PL", name="Платформы")
        self.shipment_type = ShipmentType.objects.create(
            code="ST_M",
            name="маршрутная",
        )
        self.message_type = MessageType.objects.create(code="MT_EXP", name="Экспорт")

        Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            route_code="OP-FOREST-1",
            freight_charge_rub=Decimal("1000.00"),
        )

    def test_load_forest_xlsx_reads_route_sheet(self) -> None:
        xlsx_path = _forest_xlsx_path()
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        rows = load_ipem_forest_xlsx(xlsx_path)
        self.assertGreaterEqual(len(rows), 20)
        self.assertIn("Код груза", rows[0])
        self.assertIn("Станц отпр РФ", rows[0])
        self.assertIn("Вид перевозки", rows[0])

    def test_parse_economics_from_forest_row(self) -> None:
        xlsx_path = _forest_xlsx_path()
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        rows = load_ipem_forest_xlsx(xlsx_path)
        economics = parse_ipem_coal_2026_economics_row(rows[0])
        self.assertIsNotNone(economics["market_price_per_ton"])
        self.assertIsNotNone(economics["production_cost_per_ton"])

    def test_clear_preserves_non_forest_model_routes(self) -> None:
        coal_group = CargoGroup.objects.create(name="Уголь", code=1, position=1)
        coal_cargo = Cargo.objects.create(
            code="16111",
            name="УГОЛЬ Г",
            cargo_group=coal_group,
        )

        forest_model = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-FOREST",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )
        coal_model = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-COAL",
            cargo=coal_cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )

        clear_ipem_model_routes_for_cargo_groups(self.route_set, (6,))

        self.assertFalse(Route.objects.filter(pk=forest_model.pk).exists())
        self.assertTrue(Route.objects.filter(pk=coal_model.pk).exists())

    def test_import_creates_model_route_with_forest_prefix(self) -> None:
        resolved = IpemCoal2026ResolvedRow(
            ipem_row=1,
            route_code="IPEM-LES-2026-001",
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
            enterprise_load_coefficient=Decimal("0.9"),
            fixed_retention_coefficient=Decimal("1"),
            cargo_code_3="091",
            cargo_group_izpod="Лесные грузы",
        )
        model_route = build_model_route_from_resolved_row(self.route_set, resolved)
        model_route.save()

        self.assertTrue(model_route.is_model)
        self.assertEqual(model_route.route_code, "IPEM-LES-2026-001")
        linked = link_operational_routes_to_models(self.route_set, [model_route])
        self.assertEqual(linked, 1)

    def test_import_command_dry_run(self) -> None:
        xlsx_path = _forest_xlsx_path()
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        call_command(
            "import_ipem_forest_routes",
            "--file",
            str(xlsx_path),
            "--route-set-code",
            "RZD_2026_FOREST",
            "--dry-run",
        )
        self.assertEqual(
            Route.objects.filter(route_set=self.route_set, is_model=True).count(),
            0,
        )

