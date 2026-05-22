from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from core.domain.route_analysis.dto import RouteAnalysisRequestDTO
from core.domain.route_analysis.services import RouteAnalysisService
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
from scenarios.models import (
    BTDCategory,
    BTDCategoryValue,
    InflationSet,
    InflationValue,
    Scenario,
    ScenarioPriceChangeSetting,
    TariffRule,
    TariffRuleYearValue,
)

User = get_user_model()


class RouteAnalysisServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="route_calc_user", password="pass")
        self.route_set = RouteSet.objects.create(name="RS", code="RS_ROUTE_CALC")
        self.scenario = Scenario.objects.create(
            name="Route calc scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.route = self._create_route()
        self.service = RouteAnalysisService()

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
            code=1,
            defaults={"name": "Group", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=2001,
            defaults={"name": "Cargo 2001", "cargo_group": cargo_group},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="01",
            defaults={"name": "Road"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="R",
            full_name="Region",
            type="область",
        )
        origin, _ = Station.objects.get_or_create(
            esr_code=200001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=200002,
            defaults={
                "short_name": "B",
                "full_name": "Station B",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WK2",
            defaults={"name": "Wagon"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="ST2",
            defaults={"name": "Shipment"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MT_INT",
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
            route_code="RC-001",
            rzd_cost_total_per_ton=Decimal("1000.00"),
            rzd_cost_loaded_per_ton=Decimal("700.00"),
            rzd_cost_empty_per_ton=Decimal("300.00"),
            production_cost_per_ton=Decimal("500.00"),
            operators_cost_per_ton=Decimal("100.00"),
            transshipment_cost_per_ton=Decimal("50.00"),
            market_price_per_ton=Decimal("2000.00"),
        )

    def _request(
        self,
        overrides: dict[str, dict[int, Decimal]] | None = None,
    ) -> RouteAnalysisRequestDTO:
        return RouteAnalysisRequestDTO(
            scenario_id=self.scenario.id,
            route_id=self.route.id,
            overrides=overrides,
        )

    def _row_values(self, response, key: str) -> list[str]:
        for row in response.rows:
            if row.key == key:
                return row.values
        raise AssertionError(f"Row {key} not found")

    def test_equalizer_baseline_in_response(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        keys = {item.key for item in response.equalizer.types}
        self.assertEqual(
            keys,
            {"cost", "oper", "per", "price_rub", "base", "rules"},
        )
        cost_type = next(t for t in response.equalizer.types if t.key == "cost")
        self.assertEqual(cost_type.values["2025"], "500.00")
        per_type = next(t for t in response.equalizer.types if t.key == "per")
        self.assertFalse(per_type.visible)

    def test_base_override_increases_rzd(self) -> None:
        baseline = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )
        overridden = self.service.calculate(
            request_dto=self._request(
                overrides={"base": {2026: Decimal("1.2000")}},
            ),
            scenario=self.scenario,
            route=self.route,
        )

        baseline_rzd = Decimal(self._row_values(baseline, "rzd")[1])
        overridden_rzd = Decimal(self._row_values(overridden, "rzd")[1])
        self.assertGreater(overridden_rzd, baseline_rzd)
        self.assertEqual(overridden_rzd, Decimal("1200.00"))

    def test_cost_override_changes_marginality(self) -> None:
        baseline = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )
        overridden = self.service.calculate(
            request_dto=self._request(
                overrides={"cost": {2025: Decimal("800.00")}},
            ),
            scenario=self.scenario,
            route=self.route,
        )

        baseline_margin = Decimal(
            baseline.rows[-1].values[0]["rub"],
        )
        overridden_margin = Decimal(
            overridden.rows[-1].values[0]["rub"],
        )
        self.assertLess(overridden_margin, baseline_margin)

    def test_effects_and_transport_structure_in_response(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        effect_keys = {row.key for row in response.effects.rows}
        self.assertIn("total", effect_keys)
        self.assertIn("base", effect_keys)
        self.assertIn("rules", effect_keys)

        self.assertIsNotNone(response.transport_structure)
        assert response.transport_structure is not None
        self.assertTrue(response.transport_structure.show_empty_leg)
        self.assertEqual(
            response.transport_structure.rzd_loaded_by_year["2025"],
            "700.00",
        )

    def test_rule_effects_rows_when_rules_match(self) -> None:
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule KPI",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        effect_keys = {row.key for row in response.effects.rows}
        self.assertIn(f"rule_{rule.id}", effect_keys)

    def test_rzd_loaded_increases_with_base_override(self) -> None:
        baseline = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )
        overridden = self.service.calculate(
            request_dto=self._request(
                overrides={"base": {2026: Decimal("1.2000")}},
            ),
            scenario=self.scenario,
            route=self.route,
        )

        assert baseline.transport_structure is not None
        assert overridden.transport_structure is not None
        baseline_loaded = Decimal(
            baseline.transport_structure.rzd_loaded_by_year["2026"],
        )
        overridden_loaded = Decimal(
            overridden.transport_structure.rzd_loaded_by_year["2026"],
        )
        self.assertGreater(overridden_loaded, baseline_loaded)

    def test_kpi_starts_from_second_year(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertEqual(len(response.kpi.by_year), 1)
        self.assertEqual(response.kpi.by_year[0].year, 2026)
        self.assertIsNotNone(response.kpi.by_year[0].transport.rub)
        self.assertIsNone(response.kpi.by_year[0].volume_share.rub)

    def test_invalid_override_key_rejected(self) -> None:
        dto = RouteAnalysisRequestDTO(
            scenario_id=self.scenario.id,
            route_id=self.route.id,
            overrides={"unknown": {2025: Decimal("1")}},
        )
        errors = dto.validate()
        self.assertTrue(any("unknown" in err for err in errors))

    def _attach_inflation(self, rates: dict[int, str]) -> None:
        inflation_set = InflationSet.objects.create(
            name="Тестовая инфляция",
            author=self.user,
        )
        for year, rate in rates.items():
            InflationValue.objects.create(
                inflation_set=inflation_set,
                year=year,
                rate_percent=Decimal(rate),
            )
        self.scenario.inflation_set = inflation_set
        self.scenario.save(update_fields=["inflation_set"])

    def _set_price_change_mode(self, parameter: str, mode: str) -> None:
        ScenarioPriceChangeSetting.objects.update_or_create(
            scenario=self.scenario,
            parameter=parameter,
            defaults={"mode": mode},
        )

    def test_oper_inflation_indexes_compound(self) -> None:
        self._attach_inflation({2025: "0", 2026: "10"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.OPERATORS,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        oper_values = [Decimal(v) for v in self._row_values(response, "operators")]
        self.assertEqual(oper_values[0], Decimal("100.00"))
        self.assertEqual(oper_values[1], Decimal("110.00"))

        oper_type = next(t for t in response.equalizer.types if t.key == "oper")
        self.assertEqual(oper_type.values["2025"], "100.00")
        self.assertEqual(oper_type.values["2026"], "110.00")

    def test_cost_stays_flat_when_fixed(self) -> None:
        self._attach_inflation({2025: "0", 2026: "10"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.OPERATORS,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.COST,
            ScenarioPriceChangeSetting.Mode.FIXED,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        cost_values = [Decimal(v) for v in self._row_values(response, "cost")]
        self.assertEqual(cost_values[0], Decimal("500.00"))
        self.assertEqual(cost_values[1], Decimal("500.00"))

    def test_inflation_fallback_when_set_missing(self) -> None:
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.OPERATORS,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        oper_values = [Decimal(v) for v in self._row_values(response, "operators")]
        self.assertEqual(oper_values[0], Decimal("100.00"))
        self.assertEqual(oper_values[1], Decimal("100.00"))

    def test_inflation_partial_matrix_years_use_zero_for_gaps(self) -> None:
        """Годы без значения в матрице (нет) — 0%, остальные годы индексируются."""
        self.scenario.end_year = 2028
        self.scenario.save(update_fields=["end_year"])
        self._attach_inflation({2025: "0", 2026: "5"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.OPERATORS,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        oper_values = [Decimal(v) for v in self._row_values(response, "operators")]
        self.assertEqual(oper_values[0], Decimal("100.00"))
        self.assertEqual(oper_values[1], Decimal("105.00"))
        self.assertEqual(oper_values[2], Decimal("105.00"))
        self.assertEqual(oper_values[3], Decimal("105.00"))

    def test_override_still_wins_over_inflation(self) -> None:
        self._attach_inflation({2025: "0", 2026: "10"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.OPERATORS,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )

        response = self.service.calculate(
            request_dto=self._request(
                overrides={"oper": {2026: Decimal("200.00")}},
            ),
            scenario=self.scenario,
            route=self.route,
        )

        oper_values = [Decimal(v) for v in self._row_values(response, "operators")]
        self.assertEqual(oper_values[0], Decimal("100.00"))
        self.assertEqual(oper_values[1], Decimal("200.00"))
