from decimal import Decimal
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import TestCase

from assistant.domain.tools.registry import call_tool, ensure_tools_loaded, get_tool
from core.domain.services.app_settings import AppSettingsService
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
from scenarios.models import BTDCategory, BTDCategoryValue, Scenario

User = get_user_model()


class RouteAnalysisToolsTests(TestCase):
    def setUp(self) -> None:
        ensure_tools_loaded()
        self.user = User.objects.create_user(login="assistant_tools_user", password="pass")
        self.other = User.objects.create_user(login="assistant_other", password="pass")
        self.route_set = RouteSet.objects.create(name="RS", code="RS_ASSIST")
        self.scenario = Scenario.objects.create(
            name="Assistant scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.route = self._create_route()
        category = BTDCategory.objects.create(
            name="Индексация",
            scenario=self.scenario,
            position=1,
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=category,
            year=2025,
            value=Decimal("1.0000"),
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=category,
            year=2026,
            value=Decimal("1.1000"),
        )

    def _create_route(self) -> Route:
        cargo_group, _ = CargoGroup.objects.get_or_create(
            code=91,
            defaults={"name": "Group", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=9101,
            defaults={"name": "Cargo 9101", "cargo_group": cargo_group},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="91",
            defaults={"name": "Road"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="RA",
            full_name="Region A",
            type="область",
        )
        origin, _ = Station.objects.get_or_create(
            esr_code=910001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=910002,
            defaults={
                "short_name": "B",
                "full_name": "Station B",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WK91",
            defaults={"name": "Wagon"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="ST91",
            defaults={"name": "Shipment"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MT_ASSIST",
            defaults={"name": "Внутр. перевозки"},
        )
        return Route.objects.create(
            route_set=self.route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="ASSIST-001",
            rzd_cost_total_per_ton=Decimal("1000.00"),
            production_cost_per_ton=Decimal("500.00"),
            operators_cost_per_ton=Decimal("100.00"),
            transshipment_cost_per_ton=Decimal("50.00"),
            market_price_per_ton=Decimal("2000.00"),
            transport_volume_tons=Decimal("100000"),
        )

    def test_tools_registered(self):
        self.assertIsNotNone(get_tool("get_route_summary"))
        self.assertIsNotNone(get_tool("get_kpi_summary"))
        self.assertIsNotNone(get_tool("get_margin_drivers"))

    def test_get_route_summary_ok(self):
        result = call_tool(
            "get_route_summary",
            {
                "scenario_id": self.scenario.id,
                "route_id": self.route.id,
                "user_id": self.user.id,
            },
        )
        self.assertTrue(result["success"])
        self.assertEqual(result["route"]["route_code"], "ASSIST-001")
        self.assertEqual(result["scenario"]["name"], "Assistant scenario")

    def test_acl_denies_other_user_when_share_own(self):
        with patch.object(
            AppSettingsService,
            "can_read_scenario",
            return_value=False,
        ):
            result = call_tool(
                "get_route_summary",
                {
                    "scenario_id": self.scenario.id,
                    "route_id": self.route.id,
                    "user_id": self.other.id,
                },
            )
        self.assertFalse(result["success"])
        self.assertIn("Сценарий не найден", result["errors"][0])

    def test_get_kpi_summary_compact(self):
        result = call_tool(
            "get_kpi_summary",
            {
                "scenario_id": self.scenario.id,
                "route_id": self.route.id,
                "user_id": self.user.id,
            },
        )
        self.assertTrue(result["success"])
        self.assertIn("kpi", result)
        self.assertIn("by_year", result["kpi"])
        self.assertGreaterEqual(len(result["kpi"]["by_year"]), 1)

    def test_get_tariff_coefficients(self):
        result = call_tool(
            "get_tariff_coefficients",
            {
                "scenario_id": self.scenario.id,
                "route_id": self.route.id,
                "user_id": self.user.id,
            },
        )
        self.assertTrue(result["success"])
        self.assertIn("base_coefficient_by_year", result)
        self.assertIn("2026", result["base_coefficient_by_year"])

    def test_unknown_route(self):
        result = call_tool(
            "get_route_summary",
            {
                "scenario_id": self.scenario.id,
                "route_id": 999999,
                "user_id": self.user.id,
            },
        )
        self.assertFalse(result["success"])

    def test_simulate_parameter_factor_ui_overrides(self):
        result = call_tool(
            "simulate_parameter_factor",
            {
                "scenario_id": self.scenario.id,
                "route_id": self.route.id,
                "user_id": self.user.id,
                "parameter": "price_rub",
                "factor": 2,
            },
        )
        self.assertTrue(result["success"], result)
        self.assertIn("ui_overrides", result)
        self.assertIn("price_rub", result["ui_overrides"])
        self.assertEqual(result["ui_focus_equalizer_type"], "price_rub")
        # цена ×2 относительно baseline
        baseline = result["baseline"]["parameter_by_year"]
        simulated = result["ui_overrides"]["price_rub"]
        for year, base_raw in baseline.items():
            base = float(base_raw)
            sim = float(simulated[year])
            self.assertAlmostEqual(sim, base * 2, places=3)
