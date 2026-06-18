import csv
import tempfile
from decimal import Decimal
from io import StringIO
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.management.ipem_economics import (
    IPEM_COLUMN_BY_ROUTE_FIELD,
    apply_economics_to_rzd_routes,
    build_ipem_coal_2026_overlap,
    build_ipem_match_records,
    count_rzd_routes,
    load_records_from_export_csv,
    resolve_cargo_by_etsng,
    resolve_message_type,
    resolve_wagon_kind,
    write_export_csv,
)
from core.domain.cargo.formatting import format_etsng_code
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


class IpemEconomics2025Tests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(code="RZD_2026_TEST", name="RZD test")
        cargo_group = CargoGroup.objects.create(name="G", code=99, position=1)
        self.cargo = Cargo.objects.create(
            code=99001,
            name="УГОЛЬ ТЕСТ",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="77", name="Road")
        region = Region.objects.create(
            short_name="R",
            full_name="Region",
            type="область",
        )
        self.origin = Station.objects.create(
            esr_code=111111,
            short_name="A",
            full_name="Station A",
            region=region,
            railroad=railroad,
        )
        self.destination = Station.objects.create(
            esr_code=222222,
            short_name="B",
            full_name="Station B",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_T", name="Wagon")
        self.shipment_type = ShipmentType.objects.create(code="ST_T", name="Shipment")
        self.message_type = MessageType.objects.create(code="MT_T", name="Internal")

        for idx in (1, 2):
            Route.objects.create(
                route_set=self.route_set,
                cargo=self.cargo,
                origin_station=self.origin,
                destination_station=self.destination,
                wagon_kind=self.wagon_kind,
                shipment_type=self.shipment_type,
                message_type=self.message_type,
                route_code=f"RZD-TEST-{idx}",
            )

        self.ipem_csv = self._build_ipem_csv()

    def _build_ipem_csv(self) -> Path:
        headers = [
            "index",
            "Груз",
            "Код ЕСР станции отправления",
            "Код ЕСР станции назначения",
            "КЛЮЧ_КОД_МАРШРУТА",
            *IPEM_COLUMN_BY_ROUTE_FIELD.values(),
        ]
        row = {
            "index": "1",
            "Груз": "УГОЛЬ ТЕСТ",
            "Код ЕСР станции отправления": "111111",
            "Код ЕСР станции назначения": "222222",
            "КЛЮЧ_КОД_МАРШРУТА": "111111_222222",
            IPEM_COLUMN_BY_ROUTE_FIELD["rzd_cost_loaded_per_ton"]: "700,00",
            IPEM_COLUMN_BY_ROUTE_FIELD["rzd_cost_empty_per_ton"]: "300,00",
            IPEM_COLUMN_BY_ROUTE_FIELD["rzd_cost_total_per_ton"]: "1000,00",
            IPEM_COLUMN_BY_ROUTE_FIELD["operators_cost_per_ton"]: "100,50",
            IPEM_COLUMN_BY_ROUTE_FIELD["transshipment_cost_per_ton"]: "50,25",
            IPEM_COLUMN_BY_ROUTE_FIELD["excise_or_duty_per_ton"]: "10",
            IPEM_COLUMN_BY_ROUTE_FIELD["transport_total_cost_per_ton"]: "5000",
            IPEM_COLUMN_BY_ROUTE_FIELD["production_cost_per_ton"]: "800",
            IPEM_COLUMN_BY_ROUTE_FIELD["total_cost_per_ton"]: "900",
            IPEM_COLUMN_BY_ROUTE_FIELD["market_price_per_ton"]: "2500",
        }
        tmp = tempfile.NamedTemporaryFile(
            mode="w",
            encoding="utf-8-sig",
            suffix=".csv",
            delete=False,
            newline="",
        )
        writer = csv.DictWriter(tmp, fieldnames=headers, delimiter=";")
        writer.writeheader()
        writer.writerow(row)
        tmp.close()
        return Path(tmp.name)

    def test_build_ipem_match_records_finds_two_rzd_routes(self) -> None:
        result = build_ipem_match_records(
            self.ipem_csv,
            self.route_set,
            similarity_threshold=90,
        )
        self.assertEqual(result.total_ipem_rows, 1)
        self.assertEqual(len(result.matched), 1)
        self.assertEqual(result.matched[0].rzd_match_count, 2)
        self.assertEqual(result.matched[0].economics["market_price_per_ton"], Decimal("2500"))

    def test_apply_updates_all_matching_routes(self) -> None:
        result = build_ipem_match_records(
            self.ipem_csv,
            self.route_set,
            similarity_threshold=90,
        )
        stats = apply_economics_to_rzd_routes(self.route_set, result.matched, dry_run=False)
        self.assertEqual(stats["ipem_rows_applied"], 1)
        self.assertEqual(stats["rzd_routes_updated"], 2)

        for route in Route.objects.filter(route_set=self.route_set):
            self.assertEqual(route.rzd_cost_loaded_per_ton, Decimal("700.00"))
            self.assertEqual(route.rzd_cost_empty_per_ton, Decimal("300.00"))
            self.assertEqual(route.rzd_cost_total_per_ton, Decimal("1000.00"))
            self.assertEqual(route.market_price_per_ton, Decimal("2500"))
            self.assertEqual(route.operators_cost_per_ton, Decimal("100.50"))

    def test_export_and_apply_commands(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            export_path = Path(tmp_dir) / "export.csv"
            out = StringIO()
            call_command(
                "export_ipem_rzd_economics_2025",
                "--file",
                str(self.ipem_csv),
                "--route-set-code",
                "RZD_2026_TEST",
                "--output",
                str(export_path),
                stdout=out,
            )
            self.assertTrue(export_path.exists())
            records = load_records_from_export_csv(export_path)
            self.assertEqual(len(records), 1)

            call_command(
                "apply_ipem_economics_to_rzd_2025",
                "--file",
                str(export_path),
                "--from-export",
                "--route-set-code",
                "RZD_2026_TEST",
                stdout=out,
            )
            self.assertEqual(
                Route.objects.filter(
                    route_set=self.route_set,
                    market_price_per_ton=Decimal("2500"),
                ).count(),
                2,
            )

    def tearDown(self) -> None:
        if self.ipem_csv.exists():
            self.ipem_csv.unlink()


class IpemCoal2026OverlapTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(code="RZD_2026_COAL", name="RZD coal test")
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
        self.shipment_type = ShipmentType.objects.create(code="ST_T", name="повагонная")
        self.message_type = MessageType.objects.create(code="MT_EXP", name="Экспорт")

        for idx in (1, 2, 3):
            Route.objects.create(
                route_set=self.route_set,
                cargo=self.cargo,
                origin_station=self.origin,
                destination_station=self.destination,
                wagon_kind=self.wagon_kind,
                shipment_type=self.shipment_type,
                message_type=self.message_type,
                route_code=f"COAL-TEST-{idx}",
            )

    def test_resolve_cargo_by_etsng_pads_code(self) -> None:
        cargo = resolve_cargo_by_etsng("16111")
        self.assertIsNotNone(cargo)
        self.assertEqual(format_etsng_code(cargo.code), "016111")

    def test_resolve_wagon_kind_maps_poluvagon(self) -> None:
        wagon, issue = resolve_wagon_kind("полувагон", [self.wagon_kind])
        self.assertIsNone(issue)
        self.assertEqual(wagon, self.wagon_kind)

    def test_resolve_message_type_exact(self) -> None:
        message, issue = resolve_message_type(
            "Экспорт",
            {self.message_type.name.casefold(): self.message_type},
        )
        self.assertIsNone(issue)
        self.assertEqual(message, self.message_type)

    def test_count_rzd_routes_with_wagon_and_message_filters(self) -> None:
        broad = count_rzd_routes(
            self.route_set,
            origin_esr=self.origin.esr_code,
            dest_esr=self.destination.esr_code,
            cargo_id=self.cargo.pk,
        )
        strict = count_rzd_routes(
            self.route_set,
            origin_esr=self.origin.esr_code,
            dest_esr=self.destination.esr_code,
            cargo_id=self.cargo.pk,
            wagon_kind_id=self.wagon_kind.pk,
            message_type_id=self.message_type.pk,
        )
        self.assertEqual(broad, 3)
        self.assertEqual(strict, 3)

    def test_build_ipem_coal_2026_overlap_from_xlsx(self) -> None:
        xlsx_path = (
            Path(__file__).resolve().parents[4]
            / "data"
            / "ipem"
            / "Уголь_эластика_2026.xlsx"
        )
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        rows = build_ipem_coal_2026_overlap(xlsx_path, self.route_set)
        self.assertGreater(len(rows), 0)

        chegdomyn_row = next(
            (r for r in rows if r.origin_station_name == "ЧЕГДОМЫН"),
            None,
        )
        self.assertIsNotNone(chegdomyn_row)
        self.assertEqual(chegdomyn_row.resolve_status, "ok", chegdomyn_row)
        self.assertEqual(chegdomyn_row.cargo_code, "016111")
        self.assertEqual(chegdomyn_row.rzd_match_count, 3)
        self.assertEqual(chegdomyn_row.rzd_match_count_broad, 3)
