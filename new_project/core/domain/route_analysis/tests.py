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
    ElasticityRule,
    ElasticityRulePoint,
    ElasticitySet,
    ExchangeRateSet,
    ExchangeRateValue,
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
        self.assertIsNone(response.kpi.by_year[0].elasticity.pct)

    def _attach_elasticity_rule(self) -> None:
        elasticity_set = ElasticitySet.objects.create(
            name="Route KPI elasticity",
            author=self.user,
        )
        rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Internal KPI rule",
            position=0,
            message_type=self.route.message_type,
        )
        for marginality, coefficient in (
            (Decimal("-0.10"), Decimal("1.0000")),
            (Decimal("0.00"), Decimal("0.9000")),
            (Decimal("0.10"), Decimal("0.8000")),
            (Decimal("0.20"), Decimal("0.7000")),
        ):
            ElasticityRulePoint.objects.create(
                rule=rule,
                marginality=marginality,
                coefficient=coefficient,
            )
        self.scenario.elasticity_set = elasticity_set
        self.scenario.save(update_fields=["elasticity_set"])

    def test_kpi_retention_coefficient_from_elasticity_rule(self) -> None:
        self._attach_elasticity_rule()
        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.ABSOLUTE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])
        self.route.transport_volume_tons = Decimal("1000000")
        self.route.save(update_fields=["transport_volume_tons"])

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        # price 2000 - cost 500 - rzd 1000 - oper 100 - per 50 = 350 руб. (17.5%)
        self.assertEqual(response.kpi.by_year[0].elasticity.pct, "0.8000")
        self.assertEqual(response.kpi.by_year[0].elasticity.rub, "-0.20")
        self.assertIsNotNone(response.kpi.by_year[0].marginality.pct)

    def test_kpi_retention_coefficient_relative_to_base_unchanged_margin(self) -> None:
        self._attach_elasticity_rule()
        BTDCategoryValue.objects.filter(
            scenario=self.scenario,
            year=2026,
        ).update(value=Decimal("1.0000"))
        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.RELATIVE_TO_BASE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])
        self.route.transport_volume_tons = Decimal("1000000")
        self.route.save(update_fields=["transport_volume_tons"])

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertEqual(response.kpi.by_year[0].elasticity.pct, "1.0000")
        self.assertEqual(response.kpi.by_year[0].elasticity.rub, "0.00")

    def test_kpi_retention_coefficient_without_elasticity_set(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertIsNone(response.kpi.by_year[0].elasticity.pct)

    def test_kpi_retention_coefficient_capped_by_enterprise_load(self) -> None:
        self._attach_elasticity_rule()
        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.ABSOLUTE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])
        rule = ElasticityRule.objects.get(
            elasticity_set=self.scenario.elasticity_set,
            name="Internal KPI rule",
        )
        ElasticityRulePoint.objects.filter(
            rule=rule,
            marginality=Decimal("0.10"),
        ).update(coefficient=Decimal("1.2000"))
        self.route.transport_volume_tons = Decimal("1000000")
        self.route.enterprise_load_coefficient = Decimal("0.9")
        self.route.save(
            update_fields=["transport_volume_tons", "enterprise_load_coefficient"],
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertEqual(response.kpi.by_year[0].elasticity.pct, "1.1000")

    def test_kpi_retention_coefficient_enterprise_load_from_model_route(self) -> None:
        self._attach_elasticity_rule()
        rule = ElasticityRule.objects.get(
            elasticity_set=self.scenario.elasticity_set,
            name="Internal KPI rule",
        )
        ElasticityRulePoint.objects.filter(
            rule=rule,
            marginality=Decimal("0.10"),
        ).update(coefficient=Decimal("1.2000"))
        model_route = Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code="MODEL-LOAD",
            cargo=self.route.cargo,
            origin_station=self.route.origin_station,
            destination_station=self.route.destination_station,
            wagon_kind=self.route.wagon_kind,
            shipment_type=self.route.shipment_type,
            message_type=self.route.message_type,
            enterprise_load_coefficient=Decimal("0.9"),
        )
        self.route.model_route = model_route
        self.route.transport_volume_tons = Decimal("1000000")
        self.route.save(update_fields=["model_route", "transport_volume_tons"])

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=Route.objects.select_related("model_route").get(pk=self.route.pk),
        )

        self.assertEqual(response.kpi.by_year[0].elasticity.pct, "1.1000")

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

    def _create_export_route(self) -> Route:
        message_type, _ = MessageType.objects.get_or_create(
            code="MT_EXP",
            defaults={"name": "Экспорт"},
        )
        self.route.message_type = message_type
        self.route.market_price_per_ton = Decimal("2000.00")
        self.route.save(update_fields=["message_type", "market_price_per_ton"])
        return self.route

    def _attach_fx(self, rates: dict[int, str]) -> None:
        fx_set = ExchangeRateSet.objects.create(
            name="Тестовый курс",
            author=self.user,
        )
        for year, rate in rates.items():
            ExchangeRateValue.objects.create(
                rate_set=fx_set,
                year=year,
                usd_rub=Decimal(rate),
            )
        self.scenario.exchange_rate_set = fx_set
        self.scenario.save(update_fields=["exchange_rate_set"])

    def test_export_by_fx_converts_market_price(self) -> None:
        export_route = self._create_export_route()
        self.scenario.export_price_mode = Scenario.ExportPriceMode.BY_FX
        self.scenario.save(update_fields=["export_price_mode"])
        self._attach_fx({2025: "100", 2026: "110"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.MARKET_PRICE,
            ScenarioPriceChangeSetting.Mode.FIXED,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=export_route,
        )

        price_values = [Decimal(v) for v in self._row_values(response, "price_rub")]
        usd_y0 = Decimal("2000.00") / Decimal("100")
        self.assertEqual(price_values[0], Decimal("2000.00"))
        self.assertEqual(price_values[1], _quantize(usd_y0 * Decimal("110")))

        fx_type = next(t for t in response.equalizer.types if t.key == "fx")
        self.assertTrue(fx_type.visible)
        self.assertTrue(fx_type.editable)
        self.assertEqual(Decimal(fx_type.values["2025"]), Decimal("100"))

    def test_export_by_fx_with_inflation_in_usd(self) -> None:
        export_route = self._create_export_route()
        self.scenario.export_price_mode = Scenario.ExportPriceMode.BY_FX
        self.scenario.save(update_fields=["export_price_mode"])
        self._attach_fx({2025: "100", 2026: "100"})
        self._attach_inflation({2025: "0", 2026: "10"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.MARKET_PRICE,
            ScenarioPriceChangeSetting.Mode.INFLATION,
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=export_route,
        )

        price_values = [Decimal(v) for v in self._row_values(response, "price_rub")]
        usd_y0 = Decimal("2000.00") / Decimal("100")
        self.assertEqual(price_values[0], Decimal("2000.00"))
        self.assertEqual(price_values[1], _quantize(usd_y0 * Decimal("1.1") * Decimal("100")))

    def test_export_fx_equalizer_notice_without_rate_set(self) -> None:
        export_route = self._create_export_route()
        self.scenario.export_price_mode = Scenario.ExportPriceMode.BY_FX
        self.scenario.save(update_fields=["export_price_mode"])

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=export_route,
        )

        fx_type = next(t for t in response.equalizer.types if t.key == "fx")
        self.assertFalse(fx_type.editable)
        self.assertIn("не прикреплён", fx_type.notice.lower())

    def test_internal_route_has_no_fx_equalizer(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )
        keys = {item.key for item in response.equalizer.types}
        self.assertNotIn("fx", keys)

    def test_fx_override_changes_market_price(self) -> None:
        export_route = self._create_export_route()
        self.scenario.export_price_mode = Scenario.ExportPriceMode.BY_FX
        self.scenario.save(update_fields=["export_price_mode"])
        self._attach_fx({2025: "100", 2026: "100"})
        self._set_price_change_mode(
            ScenarioPriceChangeSetting.Parameter.MARKET_PRICE,
            ScenarioPriceChangeSetting.Mode.FIXED,
        )

        response = self.service.calculate(
            request_dto=self._request(
                overrides={"fx": {2026: Decimal("200")}},
            ),
            scenario=self.scenario,
            route=export_route,
        )

        price_values = [Decimal(v) for v in self._row_values(response, "price_rub")]
        usd_y0 = Decimal("2000.00") / Decimal("100")
        self.assertEqual(price_values[1], _quantize(usd_y0 * Decimal("200")))

    def test_rzd_tariff_sensitivity_at_zero_relative_mode(self) -> None:
        self._attach_elasticity_rule()

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        zero_point = next(
            point
            for point in response.rzd_tariff_sensitivity.points
            if point.change_pct == "0"
        )
        self.assertEqual(zero_point.coefficient, "1.0000")

    def test_rzd_tariff_sensitivity_without_elasticity(self) -> None:
        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertEqual(response.rzd_tariff_sensitivity.points, [])

    def test_rzd_tariff_sensitivity_in_response(self) -> None:
        self._attach_elasticity_rule()

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        self.assertEqual(len(response.rzd_tariff_sensitivity.points), 101)
        payload = response.to_api_dict()
        self.assertIn("rzd_tariff_sensitivity", payload)
        self.assertEqual(len(payload["rzd_tariff_sensitivity"]["points"]), 101)

    def test_rzd_tariff_sensitivity_curve_responds_to_tariff_change(self) -> None:
        self._attach_elasticity_rule()

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        by_pct = {
            point.change_pct: point.coefficient
            for point in response.rzd_tariff_sensitivity.points
        }
        self.assertEqual(by_pct["0"], "1.0000")
        self.assertLessEqual(Decimal(by_pct["25"]), Decimal(by_pct["0"]))

    def test_rzd_tariff_sensitivity_high_margin_tariff_increase_stays_at_one(self) -> None:
        elasticity_set = ElasticitySet.objects.create(
            name="Export sensitivity",
            author=self.user,
        )
        rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Export sensitivity rule",
            position=0,
            message_type=self.route.message_type,
        )
        for marginality, coefficient in (
            (Decimal("0.05"), Decimal("1.0400")),
            (Decimal("0.13"), Decimal("1.0550")),
            (Decimal("0.23"), Decimal("1.1100")),
        ):
            ElasticityRulePoint.objects.create(
                rule=rule,
                marginality=marginality,
                coefficient=coefficient,
            )
        self.scenario.elasticity_set = elasticity_set
        self.scenario.save(update_fields=["elasticity_set"])

        self.route.market_price_per_ton = Decimal("9915.19")
        self.route.production_cost_per_ton = Decimal("2930.60")
        self.route.rzd_cost_total_per_ton = Decimal("3685.16")
        self.route.operators_cost_per_ton = Decimal("240.00")
        self.route.transshipment_cost_per_ton = Decimal("763.00")
        self.route.enterprise_load_coefficient = Decimal("0.9552")
        self.route.save(
            update_fields=[
                "market_price_per_ton",
                "production_cost_per_ton",
                "rzd_cost_total_per_ton",
                "operators_cost_per_ton",
                "transshipment_cost_per_ton",
                "enterprise_load_coefficient",
            ],
        )

        response = self.service.calculate(
            request_dto=self._request(),
            scenario=self.scenario,
            route=self.route,
        )

        by_pct = {
            point.change_pct: point.coefficient
            for point in response.rzd_tariff_sensitivity.points
        }
        self.assertEqual(by_pct["0"], "1.0000")
        self.assertEqual(by_pct["25"], "1.0000")


def _quantize(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))
