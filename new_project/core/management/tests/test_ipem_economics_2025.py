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
    build_ipem_match_records,
    load_records_from_export_csv,
    write_export_csv,
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
