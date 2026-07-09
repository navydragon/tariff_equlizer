from decimal import Decimal
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.management.ipem_economics import (
    IpemCoal2026ResolvedRow,
    build_model_route_from_resolved_row,
    clear_ipem_model_routes,
    link_operational_routes_to_models,
    load_ipem_coal_2026_xlsx,
    parse_cargo_izpod_fields_from_ipem_row,
    sync_model_routes_cargo_izpod_from_operational,
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


def _ipem_xlsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "data"
        / "ipem"
        / "Уголь_эластика_2026_5.xlsx"
    )


class IpemCoal2026ImportTests(TestCase):
    def setUp(self) -> None:
        self.route_set = RouteSet.objects.create(code="RZD_2026_IMPORT", name="RZD import")
        cargo_group = CargoGroup.objects.create(name="Уголь", code=1, position=1)
        self.cargo = Cargo.objects.create(
            code="16111",
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

    def test_assign_elasticity_sources_after_model_link(self) -> None:
        from scenarios.domain.services.operational_elasticity import (
            assign_operational_elasticity_sources,
        )

        model_route = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-ELASTICITY",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
            transport_volume_tons=Decimal("10000"),
        )
        link_operational_routes_to_models(self.route_set, [model_route])
        stats = assign_operational_elasticity_sources(self.route_set)

        self.assertEqual(stats.direct_model, 2)
        self.assertEqual(
            Route.objects.operational()
            .filter(
                skip_elasticity=False,
                elasticity_source=Route.ElasticitySource.DIRECT_MODEL,
            )
            .count(),
            2,
        )

    def test_parse_cargo_izpod_fields_from_ipem_row(self) -> None:
        fields = parse_cargo_izpod_fields_from_ipem_row(
            {
                "Код груза": "16111",
                "Группа груза": "Уголь каменный",
            },
            self.cargo,
        )
        self.assertEqual(fields["cargo_code_3"], "161")
        self.assertEqual(fields["cargo_group_izpod"], "Уголь каменный")
        self.assertEqual(fields["cargo_code_izpod"], "")
        self.assertEqual(fields["cargo_code_izpod_3"], "")

    def test_parse_economics_defaults_transshipment_and_excise_to_zero(self) -> None:
        from core.management.ipem_economics import parse_ipem_coal_2026_economics_row

        economics = parse_ipem_coal_2026_economics_row(
            {
                "Расходы по оплате услуг операторов, руб. за тонну": "100",
                "Расходы на перевалку, руб. за тонну": "",
                "Акциз/пошлина": "",
            },
        )
        self.assertEqual(economics["transshipment_cost_per_ton"], Decimal("0"))
        self.assertEqual(economics["excise_or_duty_per_ton"], Decimal("0"))
        self.assertEqual(economics["operators_cost_per_ton"], Decimal("100"))

    def test_parse_economics_reads_export_rzd_total_column_alias(self) -> None:
        from core.management.ipem_economics import parse_ipem_coal_2026_economics_row

        economics = parse_ipem_coal_2026_economics_row(
            {
                (
                    "Расходы по оплате услуг ОАО 'РЖД', руб. за тонну общая стоимость "
                    "(тарифные условия 2026 года)"
                ): "1215.07",
            },
        )
        self.assertEqual(economics["rzd_cost_total_per_ton"], Decimal("1215.07"))

    def test_load_ipem_coal_2026_xlsx_reads_both_route_sheets(self) -> None:
        xlsx_path = _ipem_xlsx_path()
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        rows = load_ipem_coal_2026_xlsx(xlsx_path)
        self.assertEqual(len(rows), 48)
        message_types = {row.get("Вид перевозки", "") for row in rows}
        self.assertIn("Экспорт", message_types)
        self.assertIn("Внутр. перевозки", message_types)

    def test_sync_cargo_izpod_from_linked_operational(self) -> None:
        model_route = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-IZPOD",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )
        operational = Route.objects.operational().first()
        self.assertIsNotNone(operational)
        operational.cargo_code_izpod = "16222"
        operational.cargo_group_izpod = "Уголь каменный"
        operational.cargo_code_3 = "161"
        operational.cargo_code_izpod_3 = "162"
        operational.model_route = model_route
        operational.save(
            update_fields=[
                "cargo_code_izpod",
                "cargo_group_izpod",
                "cargo_code_3",
                "cargo_code_izpod_3",
                "model_route",
            ],
        )

        updated = sync_model_routes_cargo_izpod_from_operational(
            self.route_set,
            [model_route],
        )
        self.assertEqual(updated, 1)
        model_route.refresh_from_db()
        self.assertEqual(model_route.cargo_code_izpod, "16222")
        self.assertEqual(model_route.cargo_group_izpod, "Уголь каменный")
        self.assertEqual(model_route.cargo_code_3, "161")
        self.assertEqual(model_route.cargo_code_izpod_3, "162")

    def test_parse_enterprise_load_coefficient_from_unnamed_column(self) -> None:
        from core.management.ipem_economics import parse_enterprise_load_coefficient

        self.assertEqual(
            parse_enterprise_load_coefficient({"Unnamed: 45": "0.875"}),
            Decimal("0.875"),
        )
        self.assertEqual(
            parse_enterprise_load_coefficient({"Unnamed: 46": "1.0"}),
            Decimal("1.0"),
        )
        self.assertEqual(
            parse_enterprise_load_coefficient(
                {"Коэффициент загрузки предприятия": "0.9"},
            ),
            Decimal("0.9"),
        )
        self.assertIsNone(parse_enterprise_load_coefficient({}))

    def test_parse_fixed_retention_from_internal_logistics_marker(self) -> None:
        from core.management.ipem_economics import parse_fixed_retention_coefficient

        self.assertEqual(
            parse_fixed_retention_coefficient(
                {"Коэффициент загрузки предприятия": "Внутренняя логистика"},
            ),
            Decimal("1"),
        )
        self.assertEqual(
            parse_fixed_retention_coefficient(
                {"Коэффициент загрузки предприятия": "  внутренняя ЛОГИСТИКА  "},
            ),
            Decimal("1"),
        )
        self.assertIsNone(parse_fixed_retention_coefficient({}))
        self.assertIsNone(
            parse_fixed_retention_coefficient({"Коэффициент загрузки предприятия": "0.9"}),
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
            enterprise_load_coefficient=Decimal("0.9"),
            fixed_retention_coefficient=Decimal("1"),
            cargo_code_3="161",
            cargo_group_izpod="Уголь каменный",
        )
        clear_ipem_model_routes(self.route_set)
        model_route = build_model_route_from_resolved_row(self.route_set, resolved)
        model_route.save()

        self.assertTrue(model_route.is_model)
        self.assertIsNone(model_route.model_route_id)
        self.assertEqual(model_route.market_price_per_ton, Decimal("5000.00"))
        self.assertEqual(model_route.enterprise_load_coefficient, Decimal("0.9"))
        self.assertEqual(model_route.fixed_retention_coefficient, Decimal("1"))
        self.assertEqual(model_route.cargo_code_3, "161")
        self.assertEqual(model_route.cargo_group_izpod, "Уголь каменный")
        linked = link_operational_routes_to_models(self.route_set, [model_route])
        self.assertEqual(linked, 2)

    def test_clear_preserves_non_coal_model_routes(self) -> None:
        other_group = CargoGroup.objects.create(name="Нефть", code=3, position=3)
        other_cargo = Cargo.objects.create(
            code="021001",
            name="НЕФТЬ",
            cargo_group=other_group,
        )
        coal_model = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-COAL",
            cargo=self.cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )
        other_model = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-OIL",
            cargo=other_cargo,
            origin_station=self.origin,
            destination_station=self.destination,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=self.message_type,
        )
        operational = Route.objects.operational().first()
        self.assertIsNotNone(operational)
        operational.model_route = other_model
        operational.save(update_fields=["model_route"])

        clear_ipem_model_routes(self.route_set)

        self.assertFalse(Route.objects.filter(pk=coal_model.pk).exists())
        self.assertTrue(Route.objects.filter(pk=other_model.pk).exists())
        operational.refresh_from_db()
        self.assertEqual(operational.model_route_id, other_model.pk)

    def test_import_command_dry_run(self) -> None:
        xlsx_path = _ipem_xlsx_path()
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


def _metallurgy_xlsx_path() -> Path:
    return (
        Path(__file__).resolve().parents[4]
        / "data"
        / "ipem"
        / "Металлургия_эластика.xlsx"
    )


class IpemMetallurgyEconomicsImportTests(TestCase):
    def test_load_metallurgy_xlsx_reads_pasted_economics_values(self) -> None:
        from core.management.ipem_economics import (
            load_ipem_metallurgy_2026_xlsx,
            parse_ipem_coal_2026_economics_row,
        )

        xlsx_path = _metallurgy_xlsx_path()
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        rows = load_ipem_metallurgy_2026_xlsx(xlsx_path)
        self.assertGreaterEqual(len(rows), 100)

        economics = parse_ipem_coal_2026_economics_row(rows[0])
        self.assertIsNotNone(economics["market_price_per_ton"])
        self.assertIsNotNone(economics["production_cost_per_ton"])
        self.assertIsNotNone(economics["operators_cost_per_ton"])
        self.assertIsNotNone(economics["total_cost_per_ton"])

        for field in (
            "market_price_per_ton",
            "production_cost_per_ton",
            "operators_cost_per_ton",
            "transport_total_cost_per_ton",
            "total_cost_per_ton",
        ):
            filled = sum(
                1
                for row in rows
                if parse_ipem_coal_2026_economics_row(row)[field] is not None
            )
            self.assertGreaterEqual(filled, len(rows) - 5, msg=field)
