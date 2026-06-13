import json
from decimal import Decimal

import pandas as pd
from django.contrib.auth import get_user_model
from django.core.cache import cache
from django.test import Client, TestCase
from django.urls import reverse

from calculations.domain.dto.scenario_absolute import ScenarioAbsoluteRequestDTO
from calculations.domain.dto.scenario_effects import (
    ScenarioEffectsAggregateRequestDTO,
    ScenarioEffectsRequestDTO,
)
from calculations.domain.dto.scenario_effects_cube import (
    ScenarioEffectsCubeRequestDTO,
)
from calculations.domain.services import (
    ScenarioAbsoluteService,
    ScenarioEffectsCubeService,
    ScenarioEffectsPandasService,
    ScenarioEffectsService,
    TariffLoadService,
)
from calculations.domain.services.scenario_effects_cache import get_payload, get_payload_ready
from calculations.domain.services.pandas_tariff_conditions import (
    build_rule_mask,
    build_rule_mask_numpy,
)
from scenarios.domain.utils.tariff_conditions import apply_tariff_conditions
from core.domain.services.app_settings import SHARE_MODE_ALL, SHARE_MODE_OWN, SHARE_SCENARIOS_CODE
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    Setting,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)
from scenarios.models import (
    BTDCategory,
    BTDCategoryValue,
    Scenario,
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)

User = get_user_model()


class TariffLoadServiceTestMixin:
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="calc_user", password="pass")
        self.route_set = RouteSet.objects.create(name="RS", code="RS_CALC")
        self.scenario = Scenario.objects.create(
            name="Calc scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = TariffLoadService()
        self.route = self._create_route(rzd=Decimal("1000.00"))

    def _create_route(
        self,
        *,
        rzd: Decimal,
        cargo_code: int = 1001,
        route_code: str = "R-001",
    ) -> Route:
        cargo_group, _ = CargoGroup.objects.get_or_create(
            code=1,
            defaults={"name": "Group", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=cargo_code,
            defaults={"name": f"Cargo {cargo_code}", "cargo_group": cargo_group},
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
            esr_code=100001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=100002,
            defaults={
                "short_name": "B",
                "full_name": "Station B",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WK",
            defaults={"name": "Wagon"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="ST",
            defaults={"name": "Shipment"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MT",
            defaults={"name": "Message"},
        )
        return Route.objects.create(
            route_set=self.route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code=route_code,
            rzd_cost_total_per_ton=rzd,
        )


class TariffLoadBtdOnlyTests(TariffLoadServiceTestMixin, TestCase):
    def test_rzd_grows_by_btd_coefficient(self) -> None:
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
            value=Decimal("1.1250"),
        )

        result = self.service.calculate_route(scenario=self.scenario, route=self.route)

        self.assertEqual(result.rzd_by_year[2025], Decimal("1000.00"))
        self.assertEqual(result.rzd_by_year[2026], Decimal("1125.00"))
        self.assertEqual(result.base_coefficient_by_year[2026], Decimal("1.1250"))
        self.assertEqual(result.rules_coefficient_by_year[2026], Decimal("1"))


class TariffLoadBtdAndRulesTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
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

    def test_rzd_with_matching_rule(self) -> None:
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule 1",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        result = self.service.calculate_route(scenario=self.scenario, route=self.route)

        # 1000 * (1.1 + 1.05 - 1) = 1150
        self.assertEqual(result.rzd_by_year[2026], Decimal("1150.00"))
        self.assertEqual(result.rules_coefficient_by_year[2026], Decimal("1.0500"))

    def test_rule_not_applied_when_condition_mismatch(self) -> None:
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule cargo filter",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            parameter="cargo_code",
            operator="include",
            values=[9999],
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.5000"),
        )

        result = self.service.calculate_route(scenario=self.scenario, route=self.route)

        self.assertEqual(result.rzd_by_year[2026], Decimal("1100.00"))
        self.assertEqual(result.rules_coefficient_by_year[2026], Decimal("1"))


class TariffLoadMiscTests(TariffLoadServiceTestMixin, TestCase):
    def test_empty_btd_coefficient_treated_as_one(self) -> None:
        BTDCategory.objects.create(
            name="Индексация",
            scenario=self.scenario,
            position=1,
        )

        result = self.service.calculate_route(scenario=self.scenario, route=self.route)

        self.assertEqual(result.rzd_by_year[2025], Decimal("1000.00"))
        self.assertEqual(result.rzd_by_year[2026], Decimal("1000.00"))

    def test_calculate_routes_multiple(self) -> None:
        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
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
            value=Decimal("1.2000"),
        )

        results = self.service.calculate_routes(
            scenario=self.scenario,
            routes=[self.route, route2],
        )

        self.assertEqual(len(results), 2)
        self.assertEqual(results[0].rzd_by_year[2026], Decimal("1200.00"))
        self.assertEqual(results[1].rzd_by_year[2026], Decimal("600.00"))

    def test_tariff_load_increments(self) -> None:
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

        result = self.service.calculate_route(scenario=self.scenario, route=self.route)

        self.assertEqual(result.tariff_load.total[2025], Decimal("0"))
        self.assertEqual(result.tariff_load.base[2026], Decimal("100.00"))
        self.assertEqual(result.tariff_load.total[2026], Decimal("100.00"))

    def test_base_coef_override_parameter(self) -> None:
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

        result = self.service.calculate_route(
            scenario=self.scenario,
            route=self.route,
            base_coef_overrides={2026: Decimal("1.3000")},
        )

        self.assertEqual(result.rzd_by_year[2026], Decimal("1300.00"))
        self.assertEqual(result.base_coefficient_by_year[2026], Decimal("1.3000"))


class ScenarioEffectsServiceTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.effects_service = ScenarioEffectsService()
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])

    def _setup_btd(self, coef_2026: str = "1.1000") -> None:
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
            value=Decimal(coef_2026),
        )

    def test_freight_charge_base_effect(self) -> None:
        self._setup_btd("1.1000")

        response, errors = self.effects_service.calculate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsRequestDTO(
                scenario_id=self.scenario.id,
                year=2026,
            ),
        )

        self.assertEqual(errors, [])
        self.assertIsNotNone(response)
        assert response is not None
        self.assertEqual(len(response.cards), 1)
        card = response.cards[0]
        self.assertEqual(card.year, 2026)
        self.assertEqual(card.base_bln, "0.1")
        self.assertEqual(card.base_pct, "10.0")
        self.assertEqual(card.rules_bln, "0.0")

    def test_rules_effect_on_freight_charge(self) -> None:
        self._setup_btd("1.0000")
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule 1",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        response, errors = self.effects_service.calculate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsRequestDTO(
                scenario_id=self.scenario.id,
                year=2026,
            ),
        )

        self.assertEqual(errors, [])
        assert response is not None
        self.assertEqual(response.cards[0].rules_bln, "0.1")
        self.assertEqual(response.cards[0].rules_pct, "5.0")

    def test_freight_charge_rule_breakdown(self) -> None:
        self._setup_btd("1.0000")
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule 1",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        context = self.service.build_scenario_context(self.scenario)
        effects = self.service.compute_freight_charge_effects(self.route, context)
        assert effects is not None
        self.assertEqual(effects.rules_by_year[2026], Decimal("50000000.00"))
        self.assertEqual(
            effects.rule_by_year[rule.id][2026],
            Decimal("50000000.00"),
        )

    def test_holding_filter_affects_table_not_kpi(self) -> None:
        self._setup_btd("1.1000")
        shipper_alpha, _ = Shipper.objects.get_or_create(
            okpo=1,
            inn="",
            name="Shipper Alpha",
            defaults={"holding": "Alpha"},
        )
        shipper_beta, _ = Shipper.objects.get_or_create(
            okpo=2,
            inn="",
            name="Shipper Beta",
            defaults={"holding": "Beta"},
        )
        self.route.shipper = shipper_alpha
        self.route.save(update_fields=["shipper"])

        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
        route2.freight_charge_rub = Decimal("2000000000.00")
        route2.shipper = shipper_beta
        route2.save(update_fields=["freight_charge_rub", "shipper"])

        compute_result, compute_errors = self.effects_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        self.assertEqual(compute_errors, [])
        assert compute_result is not None
        self.assertEqual(compute_result.cards[0].base_bln, "0.3")

        aggregate_result, aggregate_errors = self.effects_service.aggregate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsAggregateRequestDTO(
                cache_key=compute_result.cache_key,
                year=2026,
                holdings=["Alpha"],
            ),
        )
        self.assertEqual(aggregate_errors, [])
        assert aggregate_result is not None
        total_row = aggregate_result.table_rows[0]
        self.assertEqual(total_row.label, "ИТОГО")
        self.assertEqual(total_row.base_rub, "100000000.00")

    def test_group_by_cargo_group_table(self) -> None:
        self._setup_btd("1.1000")
        cargo_group, _ = CargoGroup.objects.get_or_create(
            code=99,
            defaults={"name": "Уголь", "position": 99},
        )
        self.route.cargo.cargo_group = cargo_group
        self.route.cargo.save(update_fields=["cargo_group"])

        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
        route2.freight_charge_rub = Decimal("500000000.00")
        route2.save(update_fields=["freight_charge_rub"])

        response, errors = self.effects_service.calculate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsRequestDTO(
                scenario_id=self.scenario.id,
                year=2026,
                group_by="cargo_group",
            ),
        )

        self.assertEqual(errors, [])
        assert response is not None
        labels = [row.label.strip() for row in response.table_rows]
        self.assertIn("ИТОГО", labels)
        self.assertTrue(any("Уголь" in label for label in labels))


class ScenarioEffectsApiTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
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

    def test_compute_api_success(self) -> None:
        url = reverse("calculations:scenario_effects_compute_api")
        response = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("cache_key", payload)
        self.assertEqual(len(payload["cards"]), 1)
        self.assertIn("filter_options", payload)

    def test_aggregate_api_success(self) -> None:
        compute_url = reverse("calculations:scenario_effects_compute_api")
        compute_response = self.client.post(
            compute_url,
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )
        cache_key = compute_response.json()["cache_key"]

        aggregate_url = reverse("calculations:scenario_effects_aggregate_api")
        response = self.client.post(
            aggregate_url,
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "year": 2026,
                    "group_by": "cargo_group",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("table", payload)
        self.assertIn("chart", payload)

    def test_legacy_api_success(self) -> None:
        url = reverse("calculations:scenario_effects_api")
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "year": 2026,
                    "group_by": "cargo_group",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(len(payload["cards"]), 1)
        self.assertIn("table", payload)
        self.assertIn("chart", payload)

    def test_api_requires_login(self) -> None:
        client = Client()
        url = reverse("calculations:scenario_effects_api")
        response = client.post(
            url,
            data=json.dumps({"scenario_id": self.scenario.id, "year": 2026}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 302)

    def test_api_invalid_year(self) -> None:
        url = reverse("calculations:scenario_effects_api")
        response = self.client.post(
            url,
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "year": 2025,
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])


class ScenarioAbsoluteServiceTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.effects_service = ScenarioEffectsService()
        self.absolute_service = ScenarioAbsoluteService()
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.transport_volume_tons = Decimal("1500000")
        self.route.save(
            update_fields=["freight_charge_rub", "transport_volume_tons"],
        )

    def _setup_btd(self, coef_2026: str = "1.1000") -> None:
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
            value=Decimal(coef_2026),
        )

    def test_revenues_aggregate_by_year(self) -> None:
        self._setup_btd("1.1000")

        compute_result, _ = self.effects_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        assert compute_result is not None

        response, errors = self.absolute_service.aggregate_revenues(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioAbsoluteRequestDTO(
                cache_key=compute_result.cache_key,
                group_by="cargo_group",
            ),
        )

        self.assertEqual(errors, [])
        assert response is not None
        self.assertEqual(response.years, [2025, 2026])
        total_row = response.rows[0]
        self.assertEqual(total_row.label, "ИТОГО")
        self.assertEqual(total_row.years["2025"], "1.00")
        self.assertEqual(total_row.years["2026"], "1.10")

    def test_volumes_static_across_years(self) -> None:
        self._setup_btd("1.1000")

        compute_result, _ = self.effects_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        assert compute_result is not None

        response, errors = self.absolute_service.aggregate_volumes(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioAbsoluteRequestDTO(
                cache_key=compute_result.cache_key,
                group_by="holding",
            ),
        )

        self.assertEqual(errors, [])
        assert response is not None
        total_row = response.rows[0]
        self.assertEqual(total_row.years["2025"], total_row.years["2026"])
        self.assertEqual(total_row.years["2025"], "1.50")
        self.assertEqual(total_row.total, "3.00")

    def test_nested_group_by_holding(self) -> None:
        self._setup_btd("1.0000")
        shipper_alpha, _ = Shipper.objects.get_or_create(
            okpo=11,
            inn="",
            name="Shipper Alpha nested",
            defaults={"holding": "Alpha"},
        )
        shipper_beta, _ = Shipper.objects.get_or_create(
            okpo=12,
            inn="",
            name="Shipper Beta nested",
            defaults={"holding": "Beta"},
        )
        self.route.shipper = shipper_alpha
        self.route.save(update_fields=["shipper"])

        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
        route2.freight_charge_rub = Decimal("2000000000.00")
        route2.transport_volume_tons = Decimal("2000000")
        route2.shipper = shipper_beta
        route2.save(
            update_fields=[
                "freight_charge_rub",
                "transport_volume_tons",
                "shipper",
            ],
        )

        compute_result, _ = self.effects_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        assert compute_result is not None

        response, errors = self.absolute_service.aggregate_volumes(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioAbsoluteRequestDTO(
                cache_key=compute_result.cache_key,
                group_by="holding",
                group_by_inner="cargo_group",
            ),
        )

        self.assertEqual(errors, [])
        assert response is not None
        labels = [row.label.strip() for row in response.rows]
        self.assertIn("ИТОГО", labels)
        self.assertTrue(any(label == "Alpha" for label in labels))


class ScenarioEffectsPandasParityTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.python_service = ScenarioEffectsService()
        self.pandas_service = ScenarioEffectsPandasService()
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])

    def _setup_btd(self, coef_2026: str = "1.1000") -> None:
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
            value=Decimal(coef_2026),
        )

    def _assert_aggregate_close(
        self,
        python_result,
        pandas_result,
    ) -> None:
        service = ScenarioEffectsService()
        aggregate_request = ScenarioEffectsAggregateRequestDTO(
            cache_key=python_result.cache_key,
            year=2026,
            group_by="cargo_group",
            group_by_inner="none",
        )
        python_aggregate, _ = service.aggregate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=aggregate_request,
        )
        aggregate_request = ScenarioEffectsAggregateRequestDTO(
            cache_key=pandas_result.cache_key,
            year=2026,
            group_by="cargo_group",
            group_by_inner="none",
        )
        pandas_aggregate, _ = service.aggregate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=aggregate_request,
        )
        assert python_aggregate is not None
        assert pandas_aggregate is not None
        self.assertEqual(
            python_aggregate.table_rows[0].total_rub,
            pandas_aggregate.table_rows[0].total_rub,
        )

    def test_parity_btd_only(self) -> None:
        self._setup_btd("1.1000")

        python_result, python_errors = self.python_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        pandas_result, pandas_errors, meta = self.pandas_service.compute_pandas(
            scenario=self.scenario,
            user_id=self.user.id,
        )

        self.assertEqual(python_errors, [])
        self.assertEqual(pandas_errors, [])
        assert python_result is not None
        assert pandas_result is not None
        self.assertEqual(python_result.baseline_rub, pandas_result.baseline_rub)
        self.assertEqual(python_result.cards[0].base_bln, pandas_result.cards[0].base_bln)
        self.assertEqual(python_result.cards[0].rules_bln, pandas_result.cards[0].rules_bln)
        self.assertEqual(meta["engine"], "pandas")
        self._assert_aggregate_close(python_result, pandas_result)

    def test_parity_with_rule(self) -> None:
        self._setup_btd("1.0000")
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Rule 1",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        python_result, python_errors = self.python_service.compute(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        pandas_result, pandas_errors, meta = self.pandas_service.compute_pandas(
            scenario=self.scenario,
            user_id=self.user.id,
        )

        self.assertEqual(python_errors, [])
        self.assertEqual(pandas_errors, [])
        assert python_result is not None
        assert pandas_result is not None
        self.assertEqual(python_result.cards[0].rules_bln, pandas_result.cards[0].rules_bln)
        self.assertEqual(python_result.cards[0].rules_pct, pandas_result.cards[0].rules_pct)
        self.assertEqual(meta["engine"], "pandas")
        self._assert_aggregate_close(python_result, pandas_result)

    def test_scenario_snapshot_cache_hit(self) -> None:
        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )

        result_first, _, meta_first = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        get_payload_ready(result_first.cache_key)
        _, _, meta_second = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )

        self.assertFalse(meta_first.get("scenario_compute_cache_hit"))
        self.assertTrue(meta_second.get("scenario_compute_cache_hit"))
        self.assertIn("data_version", meta_second)
        self.assertEqual(meta_second["timings"]["compute_ms"], 0)

    def test_route_mart_parquet_cache_hit(self) -> None:
        from calculations.domain.services.scenario_compute_store import (
            scenario_compute_dir,
        )
        from calculations.domain.services.route_mart_store import route_mart_cache_dir
        import shutil

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        shutil.rmtree(
            route_mart_cache_dir(route_set_id=scenario.route_set_id),
            ignore_errors=True,
        )
        _, _, meta_first = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        data_version = meta_first.get("data_version")
        assert data_version

        shutil.rmtree(
            scenario_compute_dir(scenario_id=scenario.id, data_version=data_version),
            ignore_errors=True,
        )

        _, _, meta_second = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )

        self.assertFalse(meta_first.get("route_mart_cache_hit"))
        self.assertTrue(meta_second.get("route_mart_cache_hit"))
        self.assertFalse(meta_second.get("scenario_compute_cache_hit"))
        self.assertIn(
            meta_second["timings"].get("mart_read_mode"),
            ("charge_npy", "sidecar_npz", "parquet_columns", "parquet_full"),
        )

    def test_dims_sidecar_load_with_rules(self) -> None:
        from calculations.domain.services.route_mart_store import (
            dims_npz_path,
            masks_npz_path,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
        )
        import shutil

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Sidecar rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        shutil.rmtree(
            route_mart_cache_dir(route_set_id=scenario.route_set_id),
            ignore_errors=True,
        )
        _, _, meta_first = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        parquet_path = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
        self.assertTrue(dims_npz_path(parquet_path).is_file())
        self.assertTrue(masks_npz_path(parquet_path).is_file())

        _, _, meta_second = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        self.assertEqual(meta_second["timings"].get("mart_read_mode"), "sidecar_npz")
        self.assertIn("dims_npz_read_ms", meta_second["timings"])
        self.assertFalse(meta_first.get("route_mart_cache_hit"))
        self.assertTrue(meta_second.get("route_mart_cache_hit"))

    def test_prewarm_rule_mask_on_create(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mask_cache import try_load_rule_mask
        from calculations.domain.services.rule_mask_prewarm import prewarm_rule_mask
        from calculations.domain.services.tariff_load import TariffLoadService
        from scenarios.domain.dto import CreateTariffRuleDTO
        from scenarios.domain.services import TariffRuleService

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        fetch_routes_dataframe_cached_timed(scenario.route_set_id)

        service = TariffRuleService()
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Prewarm rule",
            base_percent="100",
            position=1,
            conditions=[
                {
                    "parameter": "cargo_group",
                    "operator": "include",
                    "values": ["—"],
                },
            ],
            year_values={"2026": "1.0500"},
        )
        created, errors = service.create_rule(dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        rule = TariffRule.objects.get(pk=created.id)
        df, _mart_meta, _ = fetch_routes_dataframe_cached_timed(scenario.route_set_id)
        conditions = TariffLoadService._rule_conditions_payload(rule)
        cached = try_load_rule_mask(
            route_set_id=scenario.route_set_id,
            rule_id=rule.id,
            conditions=conditions,
            n_routes=len(df),
        )
        self.assertIsNotNone(cached)

        self.assertTrue(prewarm_rule_mask(rule=rule))

    def test_compute_masks_cache_hit_after_prewarm(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.rule_mask_prewarm import prewarm_rule_mask

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Mask prewarm rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            parameter="cargo_group",
            operator="include",
            values=["—"],
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        fetch_routes_dataframe_cached_timed(scenario.route_set_id)
        self.assertTrue(prewarm_rule_mask(rule=rule))

        _, _, meta = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        self.assertEqual(meta["timings"].get("masks_ms"), 0)
        self.assertEqual(meta["timings"].get("mart_read_mode"), "sidecar_npz")

    def test_rule_mask_cache_hit(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mask_cache import (
            build_or_load_rule_mask,
            try_load_rule_mask,
        )
        from calculations.domain.services.tariff_load import TariffLoadService

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Mask cache rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        df, mart_meta, _timings = fetch_routes_dataframe_cached_timed(
            scenario.route_set_id,
        )
        tariff_load = TariffLoadService()
        conditions = tariff_load._rule_conditions_payload(rule)

        build_or_load_rule_mask(
            route_set_id=scenario.route_set_id,
            rule_id=rule.id,
            conditions=conditions,
            df=df,
            mart_meta=mart_meta,
        )
        cached = try_load_rule_mask(
            route_set_id=scenario.route_set_id,
            rule_id=rule.id,
            conditions=conditions,
            n_routes=len(df),
        )
        self.assertIsNotNone(cached)
        self.assertEqual(cached.shape, (len(df),))


class ScenarioEffectsComputePandasApiTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
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

    def test_compute_pandas_api_success(self) -> None:
        url = reverse("calculations:scenario_effects_compute_pandas_api")
        response = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["engine"], "pandas")
        self.assertIn("elapsed_ms", payload)
        self.assertIn("cache_key", payload)
        self.assertIn("data_version", payload)
        self.assertIn("scenario_compute_cache_hit", payload)

        get_payload_ready(payload["cache_key"])
        response_repeat = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )
        repeat_payload = response_repeat.json()
        self.assertTrue(repeat_payload["scenario_compute_cache_hit"])

    def test_pandas_session_payload_is_lightweight_and_hydrates_from_disk(self) -> None:
        url = reverse("calculations:scenario_effects_compute_pandas_api")
        response = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        cache_key = response.json()["cache_key"]

        cached = cache.get(cache_key)
        self.assertIsNotNone(cached)
        self.assertIsNone(cached.compact)
        self.assertTrue(cached.compact_pending)
        self.assertTrue(cached.data_version)

        resolved = get_payload_ready(cache_key)
        self.assertIsNotNone(resolved)
        self.assertIsNotNone(resolved.compact)
        self.assertGreater(len(resolved.compact.baseline_rub), 0)

    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.transport_volume_tons = Decimal("1000000")
        self.route.save(
            update_fields=["freight_charge_rub", "transport_volume_tons"],
        )
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

    def _compute_cache_key(self) -> str:
        response = self.client.post(
            reverse("calculations:scenario_effects_compute_api"),
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )
        return response.json()["cache_key"]

    def test_revenues_api_success(self) -> None:
        cache_key = self._compute_cache_key()
        response = self.client.post(
            reverse("calculations:scenario_absolute_revenues_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "group_by": "cargo_group",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("table", payload)

    def test_volumes_export_returns_xlsx(self) -> None:
        cache_key = self._compute_cache_key()
        response = self.client.post(
            reverse("calculations:scenario_absolute_volumes_export_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "group_by": "cargo_group",
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml",
            response["Content-Type"],
        )
        self.assertGreater(len(response.content), 100)

    def test_absolute_api_invalid_cache_key(self) -> None:
        response = self.client.post(
            reverse("calculations:scenario_absolute_revenues_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": "",
                    "group_by": "cargo_group",
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])


class ScenarioEffectsCubeApiTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)
        self.cube_service = ScenarioEffectsCubeService()
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
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
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Правило тест",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

    def _compute_cache_key(self) -> str:
        response = self.client.post(
            reverse("calculations:scenario_effects_compute_pandas_api"),
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )
        return response.json()["cache_key"]

    def test_cube_api_success(self) -> None:
        cache_key = self._compute_cache_key()
        response = self.client.post(
            reverse("calculations:scenario_effects_cube_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "group_by": "tariff_decision",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        rows = payload["table"]["rows"]
        effect_labels = {row["effect_label"] for row in rows}
        self.assertIn("Базовая индексация", effect_labels)
        self.assertIn("Отдельные тарифные решения", effect_labels)
        self.assertIn("Правило тест", effect_labels)
        self.assertEqual(payload["unit"], "млрд руб.")

    def test_cube_export_returns_xlsx(self) -> None:
        cache_key = self._compute_cache_key()
        response = self.client.post(
            reverse("calculations:scenario_effects_cube_export_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "group_by": "cargo_group",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn("spreadsheetml", response["Content-Type"])
        self.assertGreater(len(response.content), 100)

    def test_cube_api_without_matching_rules(self) -> None:
        """Куб работает, даже если ни одно правило не применилось к маршрутам."""
        TariffRule.objects.filter(scenario=self.scenario).delete()
        rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Не применяется",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            parameter="cargo_group",
            operator="include",
            values=["несуществующая_группа"],
            position=1,
        )

        cache_key = self._compute_cache_key()
        response = self.client.post(
            reverse("calculations:scenario_effects_cube_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "cache_key": cache_key,
                    "group_by": "cargo_group",
                    "group_by_inner": "none",
                },
            ),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        effect_labels = {row["effect_label"] for row in payload["table"]["rows"]}
        self.assertIn("Базовая индексация", effect_labels)
        self.assertIn("Отдельные тарифные решения", effect_labels)
        self.assertNotIn("Не применяется", effect_labels)

    def test_cube_service_tariff_decision_group(self) -> None:
        pandas_service = ScenarioEffectsPandasService()
        compute_result, errors, _meta = pandas_service.compute_pandas(
            scenario=self.scenario,
            user_id=self.user.id,
        )
        self.assertEqual(errors, [])
        assert compute_result is not None

        cube_result, cube_errors = self.cube_service.aggregate(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsCubeRequestDTO(
                cache_key=compute_result.cache_key,
                group_by="tariff_decision",
            ),
        )
        self.assertEqual(cube_errors, [])
        assert cube_result is not None
        self.assertTrue(cube_result.rows)
        self.assertEqual(cube_result.rows[0].group_label, "ИТОГО")


class ShareScenariosCalculationsApiTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        Setting.objects.filter(code=SHARE_SCENARIOS_CODE).delete()
        self.foreign_user = User.objects.create_user(login="foreign", password="pass")
        self.foreign_scenario = Scenario.objects.create(
            name="Foreign scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.foreign_user,
        )
        self.client = Client()
        self.client.force_login(self.user)

    def _set_share_mode(self, mode: str) -> None:
        Setting.objects.update_or_create(
            code=SHARE_SCENARIOS_CODE,
            defaults={"description": "", "value": mode},
        )

    def test_compute_foreign_scenario_all_mode_success(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        url = reverse("calculations:scenario_effects_compute_api")
        response = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.foreign_scenario.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertTrue(response.json()["success"])

    def test_compute_foreign_scenario_own_mode_not_found(self) -> None:
        self._set_share_mode(SHARE_MODE_OWN)
        url = reverse("calculations:scenario_effects_compute_api")
        response = self.client.post(
            url,
            data=json.dumps({"scenario_id": self.foreign_scenario.id}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 404)


class DistanceBeltTariffConditionsTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.route_near = self._create_route(
            rzd=Decimal("100.00"),
            route_code="R-NEAR",
        )
        self.route_near.distance_belt = "0-500"
        self.route_near.save(update_fields=["distance_belt"])

        self.route_far = self._create_route(
            rzd=Decimal("200.00"),
            route_code="R-FAR",
        )
        self.route_far.distance_belt = "500-1000"
        self.route_far.save(update_fields=["distance_belt"])

        self.route_empty = self._create_route(
            rzd=Decimal("300.00"),
            route_code="R-EMPTY",
        )
        self.route_empty.distance_belt = ""
        self.route_empty.save(update_fields=["distance_belt"])

    def test_apply_tariff_conditions_include_distance_belt(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "include",
                "values": ["0-500"],
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        self.assertEqual(matched.count(), 1)
        self.assertEqual(matched.get().id, self.route_near.id)

    def test_apply_tariff_conditions_exclude_distance_belt(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "exclude",
                "values": ["500-1000"],
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_near.id, ids)
        self.assertIn(self.route_empty.id, ids)
        self.assertNotIn(self.route_far.id, ids)

    def test_build_rule_mask_distance_belt(self) -> None:
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "distance_belt": ["0-500", "500-1000", ""],
            }
        )
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "include",
                "values": ["0-500", "500-1000"],
            }
        ]
        mask = build_rule_mask(df, conditions)
        self.assertTrue(mask.iloc[0])
        self.assertTrue(mask.iloc[1])
        self.assertFalse(mask.iloc[2])

    def test_build_rule_mask_numpy_distance_belt_exclude(self) -> None:
        df = pd.DataFrame(
            {
                "id": [1, 2],
                "distance_belt": ["0-500", "500-1000"],
            }
        )
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "exclude",
                "values": ["500-1000"],
            }
        ]
        mask = build_rule_mask_numpy(df, conditions)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])

    def test_apply_tariff_conditions_distance_belt_gt_threshold(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "gt",
                "values": 100,
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_near.id, ids)
        self.assertIn(self.route_far.id, ids)
        self.assertNotIn(self.route_empty.id, ids)

    def test_apply_tariff_conditions_distance_belt_lt_threshold(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "lt",
                "values": 500,
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        self.assertEqual(matched.count(), 1)
        self.assertEqual(matched.get().id, self.route_near.id)

    def test_build_rule_mask_distance_belt_gt_threshold(self) -> None:
        df = pd.DataFrame(
            {
                "id": [1, 2, 3],
                "distance_belt": ["0-500", "500-1000", ""],
                "distance_belt_midpoint_km": [250, 750, None],
            }
        )
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "gt",
                "values": 100,
            }
        ]
        mask = build_rule_mask(df, conditions)
        self.assertTrue(mask.iloc[0])
        self.assertTrue(mask.iloc[1])
        self.assertFalse(mask.iloc[2])

    def test_build_rule_mask_numpy_distance_belt_lt_threshold(self) -> None:
        df = pd.DataFrame(
            {
                "id": [1, 2],
                "distance_belt": ["0-500", "500-1000"],
                "distance_belt_midpoint_km": [250, 750],
            }
        )
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "lt",
                "values": 500,
            }
        ]
        mask = build_rule_mask_numpy(df, conditions)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])
