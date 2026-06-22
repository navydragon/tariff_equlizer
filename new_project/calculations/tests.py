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
from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO
from scenarios.domain.services import TariffRuleService

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

    def test_btd_ignored_when_toggle_off(self) -> None:
        self.scenario.include_base_tariff_decisions = False
        self.scenario.save(update_fields=["include_base_tariff_decisions"])

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

        scenario = Scenario.objects.get(pk=self.scenario.pk)
        result = self.service.calculate_route(scenario=scenario, route=self.route)

        self.assertEqual(result.rzd_by_year[2025], Decimal("1000.00"))
        self.assertEqual(result.rzd_by_year[2026], Decimal("1000.00"))
        self.assertEqual(result.base_coefficient_by_year[2026], Decimal("1"))


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

    def test_model_routes_excluded_from_effects_loader(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_route_set_stats,
            fetch_routes_dataframe_timed,
        )

        model_route = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="MODEL-001",
        )
        model_route.is_model = True
        model_route.freight_charge_rub = Decimal("999999999.00")
        model_route.save(update_fields=["is_model", "freight_charge_rub"])

        df, _timings = fetch_routes_dataframe_timed(self.route_set.id)
        route_ids = set(df["id"].astype(int).tolist())
        self.assertIn(self.route.id, route_ids)
        self.assertNotIn(model_route.id, route_ids)

        skipped_charge, _without_volume = fetch_route_set_stats(self.route_set.id)
        self.assertEqual(skipped_charge, 0)

    def test_fetch_routes_dataframe_timed_uses_legacy_on_sqlite(self) -> None:
        from django.db import connection

        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_timed,
        )

        if connection.vendor == "postgresql":
            self.skipTest("SQLite-only assertion")

        _df, timings = fetch_routes_dataframe_timed(self.route_set.id)
        self.assertEqual(timings.get("routes_load_mode"), "legacy")

    def test_fetch_routes_postgres_copy_matches_legacy(self) -> None:
        from django.db import connection

        from calculations.domain.services.route_effects_loader import (
            _fetch_routes_dataframe_legacy,
            _fetch_routes_dataframe_postgres_copy,
        )

        if connection.vendor != "postgresql":
            self.skipTest("PostgreSQL-only parity test")

        legacy_df, _legacy_timings = _fetch_routes_dataframe_legacy(self.route_set.id)
        copy_df, copy_timings = _fetch_routes_dataframe_postgres_copy(self.route_set.id)

        self.assertEqual(copy_timings.get("routes_load_mode"), "postgres_copy")
        self.assertEqual(list(legacy_df.columns), list(copy_df.columns))
        self.assertEqual(len(legacy_df), len(copy_df))
        if legacy_df.empty:
            return

        legacy_sorted = legacy_df.sort_values("id").reset_index(drop=True)
        copy_sorted = copy_df.sort_values("id").reset_index(drop=True)
        for column in ("id", "freight_charge_rub", "cargo_group", "holding"):
            legacy_values = legacy_sorted[column].tolist()
            copy_values = copy_sorted[column].tolist()
            if column == "freight_charge_rub":
                self.assertEqual(
                    [float(value) for value in legacy_values],
                    [float(value) for value in copy_values],
                )
            else:
                self.assertEqual(legacy_values, copy_values)

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

    def test_filter_options_cargo_groups_sorted_by_position(self) -> None:
        group_a, _ = CargoGroup.objects.update_or_create(
            code=3,
            defaults={"name": "Нефтяные грузы", "position": 3},
        )
        group_b, _ = CargoGroup.objects.update_or_create(
            code=1,
            defaults={"name": "Уголь каменный", "position": 1},
        )
        self.route.cargo.cargo_group = group_b
        self.route.cargo.save(update_fields=["cargo_group"])

        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
        route2.cargo.cargo_group = group_a
        route2.cargo.save(update_fields=["cargo_group"])
        route2.freight_charge_rub = Decimal("500000000.00")
        route2.save(update_fields=["freight_charge_rub"])

        options = self.effects_service._collect_filter_options_from_db(self.scenario)
        cargo_groups = [name for name in options["cargo_groups"] if name != "—"]
        self.assertEqual(
            cargo_groups,
            ["Уголь каменный", "Нефтяные грузы"],
        )

    def test_group_by_cargo_group_table_sorted_by_position(self) -> None:
        self._setup_btd("1.1000")
        group_a, _ = CargoGroup.objects.update_or_create(
            code=3,
            defaults={"name": "Нефтяные грузы", "position": 3},
        )
        group_b, _ = CargoGroup.objects.update_or_create(
            code=1,
            defaults={"name": "Уголь каменный", "position": 1},
        )
        self.route.cargo.cargo_group = group_b
        self.route.cargo.save(update_fields=["cargo_group"])

        route2 = self._create_route(
            rzd=Decimal("500.00"),
            cargo_code=1002,
            route_code="R-002",
        )
        route2.cargo.cargo_group = group_a
        route2.cargo.save(update_fields=["cargo_group"])
        route2.freight_charge_rub = Decimal("5000000000.00")
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
        labels = [row.label.strip() for row in response.table_rows if row.label.strip() != "ИТОГО"]
        self.assertEqual(labels, ["Уголь каменный", "Нефтяные грузы"])


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

    def test_warm_status_api_success(self) -> None:
        url = reverse("calculations:scenario_warm_status_api")
        response = self.client.get(url, {"scenario_id": self.scenario.id})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("kpi_ready", payload)
        self.assertIn("compact_ready", payload)

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

    def test_collect_filter_options_resorts_cached_mart_meta(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        CargoGroup.objects.update_or_create(
            code=1,
            defaults={"name": "Уголь каменный", "position": 1},
        )
        CargoGroup.objects.update_or_create(
            code=3,
            defaults={"name": "Нефтяные грузы", "position": 3},
        )
        mart_meta = MartMeta(
            dimension_labels={},
            filter_options={
                "cargo_groups": ["Нефтяные грузы", "Уголь каменный", "—"],
                "holdings": ["Прочие"],
            },
        )
        options = self.pandas_service._collect_filter_options(
            pd.DataFrame(),
            mart_meta,
        )
        self.assertEqual(
            options["cargo_groups"],
            ["Уголь каменный", "Нефтяные грузы", "—"],
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

    def test_kpi_totals_match_full_compute(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.scenario_effects_compute import (
            compute_arrays_full,
            compute_kpi_totals,
            rule_specs_from_context,
        )

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="KPI parity rule",
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

        context = self.pandas_service._tariff_load.build_scenario_context(scenario)
        rule_specs = rule_specs_from_context(self.pandas_service._tariff_load, context)
        df, mart_meta, _timings = fetch_routes_dataframe_cached_timed(
            scenario.route_set_id,
        )

        kpi_totals, _kpi_timings = compute_kpi_totals(
            df,
            years=context.years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=mart_meta,
        )
        full_totals, _full_timings, _arrays = compute_arrays_full(
            df,
            years=context.years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=mart_meta,
        )

        self.assertEqual(kpi_totals.baseline_total, full_totals.baseline_total)
        for year in context.years:
            self.assertEqual(
                kpi_totals.charge_by_year[year],
                full_totals.charge_by_year[year],
                year,
            )
            if year == context.years[0]:
                continue
            self.assertEqual(
                kpi_totals.base_by_year[year],
                full_totals.base_by_year[year],
                year,
            )
            self.assertEqual(
                kpi_totals.rules_by_year[year],
                full_totals.rules_by_year[year],
                year,
            )

    def test_deferred_full_compute_builds_rule_by_year(self) -> None:
        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Deferred rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        result, errors, meta = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
            include_rule_breakdown=True,
        )
        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(meta["timings"].get("rule_by_year_ms"), 0)

        payload = get_payload_ready(result.cache_key)
        self.assertIsNotNone(payload)
        assert payload is not None
        self.assertIsNotNone(payload.compact)
        assert payload.compact is not None
        self.assertGreater(len(payload.compact.rule_meta), 0)
        self.assertIsNotNone(payload.compact.rule_by_year)

    def test_deferred_aggregate_skips_rule_by_year(self) -> None:
        from calculations.domain.services.scenario_compute_store import (
            RULE_BY_YEAR_FILENAME,
            METADATA_FILENAME,
            scenario_compute_dir,
        )

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Aggregate rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        result, errors, meta = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
            include_rule_breakdown=False,
        )
        self.assertEqual(errors, [])
        assert result is not None
        self.assertEqual(meta["timings"].get("rule_by_year_ms"), 0)

        payload = get_payload_ready(result.cache_key)
        self.assertIsNotNone(payload)
        assert payload is not None
        assert payload.compact is not None
        self.assertGreater(len(payload.compact.rule_meta), 0)
        self.assertIsNone(payload.compact.rule_by_year)

        data_version = meta.get("data_version")
        assert data_version
        cache_dir = scenario_compute_dir(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        metadata = json.loads((cache_dir / METADATA_FILENAME).read_text(encoding="utf-8"))
        self.assertFalse(metadata.get("include_rule_breakdown"))
        self.assertFalse((cache_dir / RULE_BY_YEAR_FILENAME).is_file())

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
            ("charge_npy", "sidecar_mmap", "parquet_columns", "parquet_full"),
        )

    def test_dims_sidecar_load_with_rules(self) -> None:
        from calculations.domain.services.route_mart_store import (
            _list_dim_npy_columns,
            _list_mask_npy_columns,
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
        self.assertTrue(_list_dim_npy_columns(parquet_path))
        self.assertTrue(_list_mask_npy_columns(parquet_path))

        _, _, meta_second = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        self.assertTrue(meta_second.get("scenario_compute_cache_hit"))
        self.assertIsNone(meta_second["timings"].get("mart_read_mode"))
        self.assertNotIn("dims_npz_read_ms", meta_second["timings"])
        self.assertFalse(meta_first.get("route_mart_cache_hit"))
        self.assertFalse(meta_second.get("route_mart_cache_hit"))

    def test_masks_sidecar_minimal_columns(self) -> None:
        import numpy as np

        from calculations.domain.services.route_mart_store import (
            MART_RULE_MASK_SIDECAR_COLUMNS,
            _list_dim_npy_columns,
            ensure_compute_sidecars,
            load_masks_npz,
            mask_npy_path,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
        )
        import shutil

        self._setup_btd("1.1000")
        scenario = Scenario.objects.select_related("route_set").get(
            pk=self.scenario.pk,
        )
        TariffRule.objects.create(
            scenario=scenario,
            name="Mask sidecar rule",
            base_percent=Decimal("100"),
            position=1,
        )

        shutil.rmtree(
            route_mart_cache_dir(route_set_id=scenario.route_set_id),
            ignore_errors=True,
        )
        self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        parquet_path = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
        mask_keys = set(load_masks_npz(parquet_path))
        self.assertTrue(mask_keys)
        self.assertTrue(mask_keys.issubset(set(MART_RULE_MASK_SIDECAR_COLUMNS)))
        self.assertFalse(mask_keys & {"cargo_code", "cargo_group", "holding", "wagon_kind"})
        self.assertFalse(
            mask_keys
            & {"shipper_holding", "origin_railroad_code", "destination_railroad_code"},
        )

        dim_keys = _list_dim_npy_columns(parquet_path)
        self.assertIn("dim_origin_railroad", dim_keys)
        self.assertIn("dim_destination_railroad", dim_keys)

        stale_path = mask_npy_path(parquet_path, "cargo_code")
        np.save(str(stale_path.with_suffix("")), np.array([1, 2], dtype=np.int32))
        self.assertFalse(ensure_compute_sidecars(parquet_path))
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )

        fetch_routes_dataframe_cached_timed(scenario.route_set_id)
        rebuilt_keys = set(load_masks_npz(parquet_path))
        self.assertNotIn("cargo_code", rebuilt_keys)
        self.assertTrue(rebuilt_keys.issubset(set(MART_RULE_MASK_SIDECAR_COLUMNS)))

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
        with self.captureOnCommitCallbacks(execute=True):
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
        result = prewarm_rule_mask(rule=rule)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.matched_routes, 0)

        _, _, meta = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        # Тайминги в тестовом окружении могут плавать; важно, что это кэш-хит,
        # а не полноценный пересчёт (должно быть «очень быстро»).
        self.assertLessEqual(meta["timings"].get("masks_ms", 999), 50)
        self.assertEqual(meta["timings"].get("mart_read_mode"), "sidecar_mmap")

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


class ScenarioRuleWarmTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.pandas_service = ScenarioEffectsPandasService()
        self.tariff_rule_service = TariffRuleService()
        self.route.freight_charge_rub = Decimal("1000000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
        cache.clear()
        from calculations.domain.services.scenario_compute_store import (
            scenario_compute_cache_root,
        )
        import shutil

        shutil.rmtree(scenario_compute_cache_root(), ignore_errors=True)

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

    def _build_mart(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )

        fetch_routes_dataframe_cached_timed(self.scenario.route_set_id)

    def test_warm_after_rule_create_saves_kpi_snapshot(self) -> None:
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_compute_store import (
            try_load_scenario_compute,
        )
        from scenarios.domain.dto import CreateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Warm rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with self.captureOnCommitCallbacks(execute=True):
            created, errors = self.tariff_rule_service.create_rule(dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        context = self.pandas_service._tariff_load.build_scenario_context(scenario)
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        bundle = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertIsNone(bundle.compact)
        self.assertGreater(bundle.global_totals.baseline_total, 0)

    def test_prewarm_rule_mask_returns_matched_routes(self) -> None:
        from calculations.domain.services.rule_mask_prewarm import prewarm_rule_mask

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Matched routes rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            parameter="wagon_kind",
            operator="include",
            values=[str(self.route.wagon_kind_id)],
            position=1,
        )

        result = prewarm_rule_mask(rule=rule)
        self.assertIsNotNone(result)
        assert result is not None
        self.assertTrue(result.ok)
        self.assertGreaterEqual(result.matched_routes, 1)

    def test_warm_status_after_rule_create(self) -> None:
        from calculations.domain.services.scenario_warm_status import get_warm_status
        from scenarios.domain.dto import CreateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Warm status rule",
            base_percent="100",
            position=1,
            conditions=[
                {
                    "parameter": "wagon_kind",
                    "operator": "include",
                    "values": [str(self.route.wagon_kind_id)],
                },
            ],
            year_values={"2026": "1.0500"},
        )
        with self.captureOnCommitCallbacks(execute=True):
            created, errors = self.tariff_rule_service.create_rule(dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        status = get_warm_status(scenario_id=scenario.id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertTrue(status["kpi_ready"])
        self.assertEqual(status["rule_id"], created.id)
        self.assertTrue(status["mask_changed"])
        self.assertGreaterEqual(status["matched_routes"], 1)

    def test_warm_status_skips_mask_phase_for_coef_only_update(self) -> None:
        from unittest.mock import patch

        from calculations.domain.services.scenario_warm_status import get_warm_status
        from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        create_dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Coef warm status rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with patch(
            "calculations.domain.services.scenario_effects_warm.schedule_deferred_full_compute",
        ):
            with self.captureOnCommitCallbacks(execute=True):
                created, errors = self.tariff_rule_service.create_rule(create_dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        with patch(
            "calculations.domain.services.scenario_effects_warm.schedule_deferred_full_compute",
        ):
            with self.captureOnCommitCallbacks(execute=True):
                updated, errors = self.tariff_rule_service.update_rule(
                    created.id,
                    UpdateTariffRuleDTO(year_values={"2026": "1.0800"}),
                    self.user,
                )
        self.assertEqual(errors, [])
        assert updated is not None

        status = get_warm_status(scenario_id=scenario.id)
        self.assertIsNotNone(status)
        assert status is not None
        self.assertTrue(status["kpi_ready"])
        self.assertFalse(status["mask_changed"])

    def test_compute_pandas_hits_kpi_only_snapshot(self) -> None:
        from scenarios.domain.dto import CreateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="KPI snapshot rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with self.captureOnCommitCallbacks(execute=True):
            self.tariff_rule_service.create_rule(dto, self.user)

        _, _, meta = self.pandas_service.compute_pandas(
            scenario=scenario,
            user_id=self.user.id,
        )
        self.assertTrue(meta.get("scenario_compute_cache_hit"))
        self.assertFalse(meta.get("compact_ready"))
        self.assertEqual(meta["timings"].get("compute_ms"), 0)

    def test_prewarm_on_create_without_conditions_field(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mask_cache import try_load_rule_mask
        from calculations.domain.services.tariff_load import TariffLoadService
        from scenarios.domain.dto import CreateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Empty conditions rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with self.captureOnCommitCallbacks(execute=True):
            created, errors = self.tariff_rule_service.create_rule(dto, self.user)
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

    def test_update_coef_triggers_kpi_warm_not_mask(self) -> None:
        from unittest.mock import patch

        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_compute_store import (
            try_load_scenario_compute,
        )
        from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        create_dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Coef update rule",
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
        with self.captureOnCommitCallbacks(execute=True):
            created, errors = self.tariff_rule_service.create_rule(create_dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        context_before = self.pandas_service._tariff_load.build_scenario_context(scenario)
        version_before = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context_before.base_coef_by_year,
            rules=context_before.rules,
        )

        with patch(
            "calculations.domain.services.scenario_effects_warm.prewarm_rule_mask",
        ) as prewarm_mock:
            with self.captureOnCommitCallbacks(execute=True):
                updated, errors = self.tariff_rule_service.update_rule(
                    created.id,
                    UpdateTariffRuleDTO(year_values={"2026": "1.0800"}),
                    self.user,
                )
        self.assertEqual(errors, [])
        assert updated is not None
        prewarm_mock.assert_not_called()

        context_after = self.pandas_service._tariff_load.build_scenario_context(scenario)
        version_after = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context_after.base_coef_by_year,
            rules=context_after.rules,
        )
        self.assertNotEqual(version_before, version_after)
        bundle = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=version_after,
        )
        self.assertIsNotNone(bundle)

    def test_delete_rule_purges_stale_snapshot(self) -> None:
        from unittest.mock import patch

        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_compute_store import (
            scenario_compute_dir,
            try_load_scenario_compute,
        )

        self._setup_btd()
        self._build_mart()
        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name="Delete warm rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with patch(
            "calculations.domain.services.scenario_effects_warm.schedule_deferred_full_compute",
        ):
            with self.captureOnCommitCallbacks(execute=True):
                created, errors = self.tariff_rule_service.create_rule(dto, self.user)
        self.assertEqual(errors, [])
        assert created is not None

        context = self.pandas_service._tariff_load.build_scenario_context(scenario)
        old_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        old_dir = scenario_compute_dir(
            scenario_id=scenario.id,
            data_version=old_version,
        )
        self.assertTrue(old_dir.is_dir())

        with self.captureOnCommitCallbacks(execute=True):
            ok, delete_errors = self.tariff_rule_service.delete_rule(
                created.id,
                self.user,
            )
        self.assertEqual(delete_errors, [])
        self.assertTrue(ok)
        self.assertFalse(old_dir.is_dir())

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.pandas_service._tariff_load.build_scenario_context(scenario)
        new_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        self.assertNotEqual(old_version, new_version)
        bundle = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=new_version,
        )
        self.assertIsNotNone(bundle)


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
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "include_rule_breakdown": True,
                },
            ),
            content_type="application/json",
        )
        cache_key = response.json()["cache_key"]
        get_payload_ready(cache_key)
        return cache_key

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

    def test_cube_tariff_decision_requires_rule_breakdown(self) -> None:
        response = self.client.post(
            reverse("calculations:scenario_effects_compute_pandas_api"),
            data=json.dumps(
                {
                    "scenario_id": self.scenario.id,
                    "include_rule_breakdown": False,
                },
            ),
            content_type="application/json",
        )
        cache_key = response.json()["cache_key"]
        get_payload_ready(cache_key)

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

        self.assertEqual(response.status_code, 400)
        self.assertFalse(response.json()["success"])
        self.assertIn("выполняется", response.json()["errors"][0].lower())

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
            include_rule_breakdown=True,
        )
        self.assertEqual(errors, [])
        assert compute_result is not None
        get_payload_ready(compute_result.cache_key)

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

    def test_build_rule_mask_numpy_cargo_group_code_via_db_lookup(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        CargoGroup.objects.get_or_create(
            code=8,
            defaults={"name": "Coal group", "position": 8},
        )
        mart_meta = MartMeta(
            dimension_labels={
                "cargo_group": ["Other", "Coal group"],
            },
        )
        df = pd.DataFrame(
            {
                "dim_cargo_group": [0, 1, 1],
                "message_type_id": [9, 9, 1],
            },
        )
        conditions = [
            {
                "parameter": "cargo_group",
                "operator": "include",
                "values": ["8"],
            },
        ]
        mask = build_rule_mask_numpy(df, conditions, mart_meta=mart_meta)
        self.assertFalse(mask[0])
        self.assertTrue(mask[1])
        self.assertTrue(mask[2])

    def test_build_rule_mask_numpy_wagon_kind_id_via_db_lookup(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        wagon_kind, _ = WagonKind.objects.get_or_create(
            name="Cisterns",
            defaults={"code": "cisterns-test"},
        )
        mart_meta = MartMeta(
            dimension_labels={
                "wagon_kind": ["Other", "Cisterns"],
            },
        )
        df = pd.DataFrame(
            {
                "dim_wagon_kind": [1, 0, 1],
            },
        )
        conditions = [
            {
                "parameter": "wagon_kind",
                "operator": "include",
                "values": [str(wagon_kind.id)],
            },
        ]
        mask = build_rule_mask_numpy(df, conditions, mart_meta=mart_meta)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])
        self.assertTrue(mask[2])

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


class SpecialContainerTypeTariffConditionsTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.route_a = self._create_route(
            rzd=Decimal("100.00"),
            route_code="R-CTA",
        )
        self.route_a.special_container_type = "ТипA"
        self.route_a.save(update_fields=["special_container_type"])

        self.route_b = self._create_route(
            rzd=Decimal("200.00"),
            route_code="R-CTB",
        )
        self.route_b.special_container_type = "ТипB"
        self.route_b.save(update_fields=["special_container_type"])

        self.route_empty = self._create_route(
            rzd=Decimal("300.00"),
            route_code="R-CTEMPTY",
        )
        self.route_empty.special_container_type = ""
        self.route_empty.save(update_fields=["special_container_type"])

    def test_apply_tariff_conditions_include_special_container_type(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "special_container_type",
                "operator": "include",
                "values": ["ТипA"],
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_a.id, ids)
        self.assertNotIn(self.route_b.id, ids)
        self.assertNotIn(self.route_empty.id, ids)

    def test_build_rule_mask_numpy_special_container_type_include(self) -> None:
        df = pd.DataFrame(
            {
                "special_container_type": ["ТипA", "ТипB", ""],
            }
        )
        conditions = [
            {
                "parameter": "special_container_type",
                "operator": "include",
                "values": ["ТипB"],
            }
        ]
        mask = build_rule_mask_numpy(df, conditions)
        self.assertFalse(mask[0])
        self.assertTrue(mask[1])
        self.assertFalse(mask[2])

    def test_tariff_rule_options_api_special_container_type(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)
        url = reverse("scenarios:tariff_rule_options", args=[self.scenario.id])
        response = self.client.get(url, {"parameter": "special_container_type"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        values = [item["value"] for item in payload["items"]]
        self.assertIn("ТипA", values)
        self.assertIn("ТипB", values)
        self.assertNotIn("", values)


class ShipmentCategoryTariffConditionsTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.route_loaded = self._create_route(
            rzd=Decimal("100.00"),
            route_code="R-SC-LOADED",
        )
        self.route_loaded.shipment_category = "груженые"
        self.route_loaded.save(update_fields=["shipment_category"])

        self.route_empty_wagon = self._create_route(
            rzd=Decimal("200.00"),
            route_code="R-SC-EMPTY",
        )
        self.route_empty_wagon.shipment_category = "порожние"
        self.route_empty_wagon.save(update_fields=["shipment_category"])

        self.route_blank = self._create_route(
            rzd=Decimal("300.00"),
            route_code="R-SC-BLANK",
        )
        self.route_blank.shipment_category = ""
        self.route_blank.save(update_fields=["shipment_category"])

    def test_apply_tariff_conditions_include_shipment_category(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "shipment_category",
                "operator": "include",
                "values": ["груженые"],
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_loaded.id, ids)
        self.assertNotIn(self.route_empty_wagon.id, ids)
        self.assertNotIn(self.route_blank.id, ids)

    def test_apply_tariff_conditions_include_shipment_category_empty_normalized(
        self,
    ) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        conditions = [
            {
                "parameter": "shipment_category",
                "operator": "include",
                "values": ["—"],
            }
        ]
        matched = apply_tariff_conditions(qs, conditions)
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_blank.id, ids)
        self.assertNotIn(self.route_loaded.id, ids)

    def test_build_rule_mask_numpy_shipment_category_via_dim_and_mart_meta(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        mart_meta = MartMeta(
            dimension_labels={
                "shipment_category": ["груженые", "порожние", "—"],
            },
        )
        df = pd.DataFrame(
            {
                "dim_shipment_category": [0, 1, 2],
            },
        )
        conditions = [
            {
                "parameter": "shipment_category",
                "operator": "include",
                "values": ["порожние"],
            }
        ]
        mask = build_rule_mask_numpy(df, conditions, mart_meta=mart_meta)
        self.assertFalse(mask[0])
        self.assertTrue(mask[1])
        self.assertFalse(mask[2])

    def test_tariff_rule_options_api_shipment_category(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)
        url = reverse("scenarios:tariff_rule_options", args=[self.scenario.id])
        response = self.client.get(url, {"parameter": "shipment_category"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        values = [item["value"] for item in payload["items"]]
        self.assertIn("груженые", values)
        self.assertIn("порожние", values)
        self.assertNotIn("", values)

    def test_data_version_changes_when_shipment_category_condition_added(self) -> None:
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO
        from scenarios.domain.services import TariffRuleService

        dto = CreateTariffRuleDTO(
            scenario_id=self.scenario.id,
            name="Before shipment filter",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        rule, errors = TariffRuleService().create_rule(dto, self.user)
        self.assertFalse(errors)
        assert rule is not None

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        before = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )

        updated, errors = TariffRuleService().update_rule(
            rule.id,
            UpdateTariffRuleDTO(
                conditions=[
                    {
                        "position": 0,
                        "parameter": "shipment_category",
                        "operator": "include",
                        "values": ["груженые"],
                    }
                ],
            ),
            self.user,
        )
        self.assertFalse(errors)
        self.assertIsNotNone(updated)

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        after = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        self.assertNotEqual(before, after)

    def test_rule_mask_cache_hit_shipment_category(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mask_cache import (
            build_or_load_rule_mask,
            try_load_rule_mask,
        )

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Shipment category mask rule",
            base_percent=Decimal("100"),
            position=1,
        )
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            position=0,
            parameter="shipment_category",
            operator="include",
            values=["груженые"],
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=rule,
            year=2026,
            coefficient=Decimal("1.0500"),
        )

        df, mart_meta, _timings = fetch_routes_dataframe_cached_timed(
            scenario.route_set_id,
        )
        conditions = [
            {
                "position": 0,
                "parameter": "shipment_category",
                "operator": "include",
                "values": ["груженые"],
            }
        ]

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


class RouteCargoIzpodTariffConditionsTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.route_a = self._create_route(
            rzd=Decimal("100.00"),
            route_code="R-IZPOD-A",
        )
        self.route_a.cargo_code_3 = "123"
        self.route_a.cargo_code_izpod_3 = "456"
        self.route_a.cargo_group_izpod = "Группа A"
        self.route_a.freight_charge_rub = Decimal("1000000.00")
        self.route_a.save(
            update_fields=[
                "cargo_code_3",
                "cargo_code_izpod_3",
                "cargo_group_izpod",
                "freight_charge_rub",
            ],
        )

        self.route_b = self._create_route(
            rzd=Decimal("200.00"),
            route_code="R-IZPOD-B",
        )
        self.route_b.cargo_code_3 = "789"
        self.route_b.cargo_code_izpod_3 = "456"
        self.route_b.cargo_group_izpod = "Группа B"
        self.route_b.freight_charge_rub = Decimal("1000000.00")
        self.route_b.save(
            update_fields=[
                "cargo_code_3",
                "cargo_code_izpod_3",
                "cargo_group_izpod",
                "freight_charge_rub",
            ],
        )

    def test_apply_tariff_conditions_include_cargo_code_3(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        matched = apply_tariff_conditions(
            qs,
            [
                {
                    "parameter": "cargo_code_3",
                    "operator": "include",
                    "values": ["123"],
                }
            ],
        )
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_a.id, ids)
        self.assertNotIn(self.route_b.id, ids)

    def test_apply_tariff_conditions_include_cargo_code_izpod_3(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        matched = apply_tariff_conditions(
            qs,
            [
                {
                    "parameter": "cargo_code_izpod_3",
                    "operator": "include",
                    "values": ["456"],
                }
            ],
        )
        ids = set(matched.values_list("id", flat=True))
        self.assertIn(self.route_a.id, ids)
        self.assertIn(self.route_b.id, ids)

    def test_apply_tariff_conditions_include_cargo_group_izpod(self) -> None:
        qs = Route.objects.filter(route_set=self.route_set)
        matched = apply_tariff_conditions(
            qs,
            [
                {
                    "parameter": "cargo_group_izpod",
                    "operator": "include",
                    "values": ["Группа B"],
                }
            ],
        )
        ids = set(matched.values_list("id", flat=True))
        self.assertNotIn(self.route_a.id, ids)
        self.assertIn(self.route_b.id, ids)

    def test_build_rule_mask_numpy_cargo_izpod_fields(self) -> None:
        df = pd.DataFrame(
            {
                "cargo_code_3": ["123", "789", ""],
                "cargo_code_izpod_3": ["456", "456", "111"],
                "cargo_group_izpod": ["Группа A", "Группа B", ""],
            }
        )
        mask_code_3 = build_rule_mask_numpy(
            df,
            [
                {
                    "parameter": "cargo_code_3",
                    "operator": "include",
                    "values": ["789"],
                }
            ],
        )
        self.assertFalse(mask_code_3[0])
        self.assertTrue(mask_code_3[1])
        self.assertFalse(mask_code_3[2])

        mask_group = build_rule_mask_numpy(
            df,
            [
                {
                    "parameter": "cargo_group_izpod",
                    "operator": "exclude",
                    "values": ["Группа B"],
                }
            ],
        )
        self.assertTrue(mask_group[0])
        self.assertFalse(mask_group[1])
        self.assertTrue(mask_group[2])

    def test_tariff_rule_options_api_cargo_izpod_fields(self) -> None:
        self.client = Client()
        self.client.force_login(self.user)
        url = reverse("scenarios:tariff_rule_options", args=[self.scenario.id])

        for parameter, expected in (
            ("cargo_code_3", "123"),
            ("cargo_code_izpod_3", "456"),
            ("cargo_group_izpod", "Группа A"),
        ):
            with self.subTest(parameter=parameter):
                response = self.client.get(url, {"parameter": parameter})
                self.assertEqual(response.status_code, 200)
                payload = response.json()
                self.assertTrue(payload["success"])
                values = [item["value"] for item in payload["items"]]
                self.assertIn(expected, values)
                self.assertNotIn("", values)

    def test_tariff_rule_options_api_cargo_group_izpod_ordered_by_position(self) -> None:
        from core.models import CargoGroup

        self.client = Client()
        self.client.force_login(self.user)
        CargoGroup.objects.create(code=91, name="Группа B", position=2)
        CargoGroup.objects.create(code=90, name="Группа A", position=1)

        url = reverse("scenarios:tariff_rule_options", args=[self.scenario.id])
        response = self.client.get(url, {"parameter": "cargo_group_izpod"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        values = [item["value"] for item in payload["items"]]
        self.assertEqual(values, ["Группа A", "Группа B"])

    def test_cargo_group_izpod_options_prefers_route_mart_labels(self) -> None:
        import shutil
        from unittest.mock import patch

        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mart_store import (
            ensure_compute_sidecars,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
        )

        self.client = Client()
        self.client.force_login(self.user)
        shutil.rmtree(route_mart_cache_dir(route_set_id=self.route_set.id), ignore_errors=True)
        fetch_routes_dataframe_cached_timed(self.route_set.id)
        parquet_path = resolve_mart_parquet_path(route_set_id=self.route_set.id)
        self.assertTrue(ensure_compute_sidecars(parquet_path))

        url = reverse("scenarios:tariff_rule_options", args=[self.scenario.id])
        with patch(
            "scenarios.domain.services.tariff_rule_options._distinct_route_values",
        ) as db_fallback:
            db_fallback.side_effect = AssertionError("unexpected DB DISTINCT fallback")
            response = self.client.get(url, {"parameter": "cargo_group_izpod"})

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        values = [item["value"] for item in payload["items"]]
        self.assertIn("Группа A", values)
        self.assertIn("Группа B", values)
        db_fallback.assert_not_called()

    def test_masks_npz_includes_cargo_izpod_sidecars(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mart_store import (
            MART_RULE_MASK_SIDECAR_COLUMNS,
            load_masks_npz,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
        )
        import shutil

        self.route_a.cargo_code_3 = "111"
        self.route_a.save(update_fields=["cargo_code_3"])

        shutil.rmtree(
            route_mart_cache_dir(route_set_id=self.route_set.id),
            ignore_errors=True,
        )
        fetch_routes_dataframe_cached_timed(self.route_set.id)
        parquet_path = resolve_mart_parquet_path(route_set_id=self.route_set.id)
        mask_keys = set(load_masks_npz(parquet_path))
        self.assertTrue(
            {"cargo_code_3", "cargo_code_izpod_3", "cargo_group_izpod"}.issubset(
                mask_keys,
            ),
        )
        self.assertTrue(mask_keys.issubset(set(MART_RULE_MASK_SIDECAR_COLUMNS)))

    def test_masks_npz_uses_compact_string_dtypes(self) -> None:
        import numpy as np

        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mart_store import (
            SIDECAR_SCHEMA_VERSION,
            _mask_sidecar_array,
            ensure_compute_sidecars,
            load_masks_npz,
            load_mart_meta,
            mask_npy_path,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
        )
        import shutil

        self.route_a.cargo_code_3 = "111"
        self.route_a.cargo_code_izpod_3 = "222"
        self.route_a.cargo_group_izpod = "Группа"
        self.route_a.special_container_type = "универсальный"
        self.route_a.save(
            update_fields=[
                "cargo_code_3",
                "cargo_code_izpod_3",
                "cargo_group_izpod",
                "special_container_type",
            ],
        )

        shutil.rmtree(
            route_mart_cache_dir(route_set_id=self.route_set.id),
            ignore_errors=True,
        )
        fetch_routes_dataframe_cached_timed(self.route_set.id)
        parquet_path = resolve_mart_parquet_path(route_set_id=self.route_set.id)
        self.assertTrue(ensure_compute_sidecars(parquet_path))

        masks = load_masks_npz(parquet_path)
        self.assertEqual(masks["cargo_code_3"].dtype, np.dtype("uint8"))
        self.assertEqual(masks["cargo_code_izpod_3"].dtype, np.dtype("uint8"))
        total_mask_bytes = sum(
            mask_npy_path(parquet_path, column).stat().st_size
            for column in masks
        )
        self.assertLess(total_mask_bytes, 50 * 1024 * 1024)

        sample = _mask_sidecar_array(
            __import__("pandas").Series(["abcdefgh"] * 1000),
            "cargo_code_3",
        )
        assert sample is not None
        self.assertEqual(sample.dtype, np.dtype("uint8"))
        meta = load_mart_meta(parquet_path)
        assert meta is not None
        self.assertEqual(meta.sidecar_schema_version, SIDECAR_SCHEMA_VERSION)

    def test_stale_parquet_without_cargo_izpod_columns_is_rebuilt(self) -> None:
        import pyarrow as pa
        import pyarrow.parquet as pq

        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mart_store import (
            MART_PARQUET_REQUIRED_COLUMNS,
            load_masks_npz,
            resolve_mart_parquet_path,
            route_mart_cache_dir,
            save_mart_meta,
            MartMeta,
        )
        import shutil

        shutil.rmtree(
            route_mart_cache_dir(route_set_id=self.route_set.id),
            ignore_errors=True,
        )

        parquet_path = resolve_mart_parquet_path(route_set_id=self.route_set.id)
        parquet_path.parent.mkdir(parents=True, exist_ok=True)
        stale_table = pa.table(
            {
                "id": [self.route_a.id],
                "freight_charge_rub": [100.0],
                "cargo_group": ["—"],
                "cargo_code": ["1001"],
                "shipment_category": ["—"],
                "park_type": ["—"],
            },
        )
        pq.write_table(stale_table, parquet_path)
        save_mart_meta(
            parquet_path=parquet_path,
            meta=MartMeta(
                dimension_labels={"cargo_group": ["—"], "cargo_code": ["1001"]},
                row_count=1,
            ),
        )

        df, meta, timings = fetch_routes_dataframe_cached_timed(self.route_set.id)
        self.assertEqual(timings.get("cache_hit"), 0)
        self.assertIn("transport_volume_tons", df.columns)
        self.assertIn("cargo_group_code", df.columns)
        self.assertTrue(MART_PARQUET_REQUIRED_COLUMNS.issubset(set(df.columns)))
        mask_keys = set(load_masks_npz(parquet_path))
        self.assertTrue(
            {"cargo_code_3", "cargo_code_izpod_3", "cargo_group_izpod"}.issubset(
                mask_keys,
            ),
        )
        self.assertIsNotNone(meta)

    def test_rule_mask_cache_hit_cargo_code_3(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.route_mask_cache import (
            build_or_load_rule_mask,
            try_load_rule_mask,
        )

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        rule = TariffRule.objects.create(
            scenario=scenario,
            name="Cargo code 3 mask rule",
            base_percent=Decimal("100"),
            position=1,
        )
        conditions = [
            {
                "position": 0,
                "parameter": "cargo_code_3",
                "operator": "include",
                "values": ["123"],
            }
        ]
        TariffRuleCondition.objects.create(
            tariff_rule=rule,
            position=0,
            parameter="cargo_code_3",
            operator="include",
            values=["123"],
        )

        df, mart_meta, _timings = fetch_routes_dataframe_cached_timed(
            scenario.route_set_id,
        )
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


class TariffRulesCacheAuditTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        cache.clear()
        from calculations.domain.services.scenario_compute_store import (
            scenario_compute_cache_root,
        )
        import shutil

        shutil.rmtree(scenario_compute_cache_root(), ignore_errors=True)

    def test_kpi_only_overwrites_stale_compact_files(self) -> None:
        import numpy as np
        from calculations.domain.services.scenario_compute_store import (
            BASELINE_RUB_FILENAME,
            METADATA_FILENAME,
            save_scenario_compute_kpi_only,
            scenario_compute_dir,
            try_load_scenario_compute,
        )
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_effects_formatting import GlobalTotals

        context = self.service.build_scenario_context(self.scenario)
        data_version = compute_scenario_data_version(
            scenario=self.scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        totals = GlobalTotals()
        totals.baseline_total = Decimal("1000")
        save_scenario_compute_kpi_only(
            scenario_id=self.scenario.id,
            data_version=data_version,
            years=[2025, 2026],
            global_totals=totals,
            filter_options={"cargo_groups": ["—"], "holdings": ["Прочие"]},
            skipped_charge=0,
            routes_without_volume=0,
        )
        cache_dir = scenario_compute_dir(
            scenario_id=self.scenario.id,
            data_version=data_version,
        )
        np.save(
            cache_dir / BASELINE_RUB_FILENAME.replace(".npy", ""),
            np.array([1.0], dtype=np.float32),
        )

        bundle = try_load_scenario_compute(
            scenario_id=self.scenario.id,
            data_version=data_version,
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertIsNone(bundle.compact)

        save_scenario_compute_kpi_only(
            scenario_id=self.scenario.id,
            data_version=data_version,
            years=[2025, 2026],
            global_totals=totals,
            filter_options={"cargo_groups": ["—"], "holdings": ["Прочие"]},
            skipped_charge=0,
            routes_without_volume=0,
        )
        self.assertFalse((cache_dir / BASELINE_RUB_FILENAME).is_file())

    def test_distance_belt_include_sidecar_ignored(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        df = pd.DataFrame(
            {
                "dim_cargo_group": [0, 1, 0],
                "distance_belt": ["0-500", "500-1000", ""],
                "distance_belt_midpoint_km": [250.0, 750.0, None],
            },
        )
        conditions = [
            {
                "parameter": "distance_belt",
                "operator": "include",
                "values": ["0-500"],
            },
        ]
        mask = build_rule_mask_numpy(df, conditions, mart_meta=MartMeta(dimension_labels={}))
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])
        self.assertFalse(mask.all())

    def test_build_rule_mask_numpy_origin_railroad_code_via_db_lookup(self) -> None:
        from calculations.domain.services.route_mart_store import MartMeta

        railroad, _ = RailRoad.objects.get_or_create(
            code="01",
            defaults={"name": "Road"},
        )
        df = pd.DataFrame(
            {
                "dim_origin_railroad": [0, 1, 0],
            },
        )
        conditions = [
            {
                "parameter": "origin_railroad",
                "operator": "include",
                "values": ["01"],
            },
        ]
        mask = build_rule_mask_numpy(
            df,
            conditions,
            mart_meta=MartMeta(
                dimension_labels={"origin_railroad": [railroad.name, "Other"]},
            ),
        )
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])

    def test_build_rule_mask_numpy_message_type_id_on_sidecar(self) -> None:
        message_type, _ = MessageType.objects.get_or_create(
            code="MT",
            defaults={"name": "Message"},
        )
        df = pd.DataFrame(
            {
                "message_type_id": [message_type.id, 999, message_type.id],
            },
        )
        conditions = [
            {
                "parameter": "message_type",
                "operator": "include",
                "values": [str(message_type.id)],
            },
        ]
        mask = build_rule_mask_numpy(df, conditions)
        self.assertTrue(mask[0])
        self.assertFalse(mask[1])
        self.assertTrue(mask[2])

    def test_kpi_only_skips_compact_cleanup_when_deferred_running(self) -> None:
        import numpy as np
        from calculations.domain.services.scenario_compute_store import (
            BASELINE_RUB_FILENAME,
            save_scenario_compute_kpi_only,
            scenario_compute_dir,
        )
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_effects_deferred import (
            DeferredFullComputeJob,
            _deferred_lock_for,
        )
        from calculations.domain.services.scenario_effects_formatting import GlobalTotals

        context = self.service.build_scenario_context(self.scenario)
        data_version = compute_scenario_data_version(
            scenario=self.scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        totals = GlobalTotals()
        cache_dir = scenario_compute_dir(
            scenario_id=self.scenario.id,
            data_version=data_version,
        )
        cache_dir.mkdir(parents=True, exist_ok=True)
        np.save(
            cache_dir / BASELINE_RUB_FILENAME.replace(".npy", ""),
            np.array([1.0], dtype=np.float32),
        )

        job = DeferredFullComputeJob(
            cache_key="",
            scenario_id=self.scenario.id,
            route_set_id=self.route_set.id,
            data_version=data_version,
            years=[2025, 2026],
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=[],
            parquet_path="",
            mask_cache_dir_path="",
            mart_meta=None,
            global_totals=totals,
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
        )
        lock = _deferred_lock_for(job)
        self.assertTrue(lock.acquire(blocking=False))
        try:
            save_scenario_compute_kpi_only(
                scenario_id=self.scenario.id,
                data_version=data_version,
                years=[2025, 2026],
                global_totals=totals,
                filter_options={"cargo_groups": ["—"], "holdings": ["Прочие"]},
                skipped_charge=0,
                routes_without_volume=0,
            )
            self.assertTrue((cache_dir / BASELINE_RUB_FILENAME).is_file())
        finally:
            lock.release()

    def test_save_and_load_compact_uses_npy_sidecars(self) -> None:
        import gc
        import numpy as np
        from calculations.domain.services.scenario_compute_store import (
            BASELINE_RUB_FILENAME,
            BASE_BY_YEAR_FILENAME,
            CHARGE_BY_YEAR_FILENAME,
            RULES_BY_YEAR_FILENAME,
            VOLUME_TONS_FILENAME,
            ScenarioComputeBundle,
            is_scenario_compact_on_disk,
            save_scenario_compute,
            scenario_compute_dir,
            try_load_scenario_compute,
        )
        from calculations.domain.services.scenario_effects_cache import (
            CompactRouteEffects,
            compute_scenario_data_version,
        )
        from calculations.domain.services.scenario_effects_formatting import GlobalTotals

        context = self.service.build_scenario_context(self.scenario)
        data_version = compute_scenario_data_version(
            scenario=self.scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        compact = CompactRouteEffects(
            years=[2025, 2026],
            dimensions={
                "cargo_group": np.array([0, 1], dtype=np.int32),
                "cargo_code": np.array([0, 1], dtype=np.int32),
                "direction": np.array([0, 0], dtype=np.int32),
                "wagon_kind": np.array([0, 0], dtype=np.int32),
                "transport_type": np.array([0, 0], dtype=np.int32),
                "shipment_category": np.array([0, 0], dtype=np.int32),
                "park_type": np.array([0, 0], dtype=np.int32),
                "holding": np.array([0, 0], dtype=np.int32),
            },
            dimension_labels={
                "cargo_group": ["A", "B"],
                "cargo_code": ["C1", "C2"],
                "direction": ["D"],
                "wagon_kind": ["W"],
                "transport_type": ["T"],
                "shipment_category": ["S"],
                "park_type": ["P"],
                "holding": ["H1"],
            },
            baseline_rub=np.array([1.0, 2.0], dtype=np.float32),
            volume_tons=np.array([3.0, 4.0], dtype=np.float32),
            base_by_year=np.array([[10.0, 11.0], [12.0, 13.0]], dtype=np.float32),
            rules_by_year=np.array([[1.0, 1.5], [2.0, 2.5]], dtype=np.float32),
            charge_by_year=np.array([[100.0, 110.0], [120.0, 130.0]], dtype=np.float32),
            rule_meta=[],
            rule_by_year=None,
        )
        totals = GlobalTotals()
        totals.baseline_total = Decimal("3")

        save_scenario_compute(
            scenario_id=self.scenario.id,
            data_version=data_version,
            bundle=ScenarioComputeBundle(
                compact=compact,
                global_totals=totals,
                filter_options={"cargo_groups": ["A", "B"], "holdings": ["H1"]},
                skipped_charge=0,
                routes_without_volume=0,
            ),
        )
        cache_dir = scenario_compute_dir(
            scenario_id=self.scenario.id,
            data_version=data_version,
        )

        for filename in (
            BASELINE_RUB_FILENAME,
            VOLUME_TONS_FILENAME,
            BASE_BY_YEAR_FILENAME,
            RULES_BY_YEAR_FILENAME,
            CHARGE_BY_YEAR_FILENAME,
        ):
            self.assertTrue((cache_dir / filename).is_file())
        self.assertTrue(is_scenario_compact_on_disk(
            scenario_id=self.scenario.id,
            data_version=data_version,
        ))

        bundle = try_load_scenario_compute(
            scenario_id=self.scenario.id,
            data_version=data_version,
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        assert bundle.compact is not None
        np.testing.assert_array_equal(bundle.compact.baseline_rub, compact.baseline_rub)
        np.testing.assert_array_equal(bundle.compact.base_by_year, compact.base_by_year)
        np.testing.assert_array_equal(bundle.compact.rules_by_year, compact.rules_by_year)
        np.testing.assert_array_equal(bundle.compact.charge_by_year, compact.charge_by_year)
        np.testing.assert_array_equal(bundle.compact.volume_tons, compact.volume_tons)
        del bundle
        del compact
        gc.collect()

    def test_rule_rename_changes_data_version(self) -> None:
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO
        from scenarios.domain.services import TariffRuleService

        dto = CreateTariffRuleDTO(
            scenario_id=self.scenario.id,
            name="Before rename",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        rule, errors = TariffRuleService().create_rule(dto, self.user)
        self.assertFalse(errors)
        assert rule is not None

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        before = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )

        updated, errors = TariffRuleService().update_rule(
            rule.id,
            UpdateTariffRuleDTO(name="After rename"),
            self.user,
        )
        self.assertFalse(errors)
        self.assertIsNotNone(updated)

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        after = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        self.assertNotEqual(before, after)

    def test_warm_deferred_updates_disk_without_session_key(self) -> None:
        from calculations.domain.services.scenario_effects_warm import (
            warm_scenario_after_rule_change,
        )
        from calculations.domain.services.scenario_compute_store import (
            try_load_scenario_compute,
        )
        from calculations.domain.services.scenario_effects_cache import (
            compute_scenario_data_version,
        )
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )

        category = BTDCategory.objects.create(name="BTD", scenario=self.scenario, position=1)
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
        self.route.freight_charge_rub = Decimal("1000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
        fetch_routes_dataframe_cached_timed(self.route_set.id)

        dto = CreateTariffRuleDTO(
            scenario_id=self.scenario.id,
            name="Warm disk rule",
            base_percent="100",
            position=1,
            conditions=[],
            year_values={"2026": "1.0500"},
        )
        with self.captureOnCommitCallbacks(execute=True):
            TariffRuleService().create_rule(dto, self.user)

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        bundle = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        self.assertIsNotNone(bundle)
        assert bundle is not None
        self.assertIsNone(bundle.compact)

        warm_scenario_after_rule_change(
            scenario_id=scenario.id,
            change="update",
            rule_id=scenario.tariff_rules.first().id,
            mask_changed=False,
        )
        bundle_after = try_load_scenario_compute(
            scenario_id=scenario.id,
            data_version=data_version,
        )
        self.assertIsNotNone(bundle_after)
        assert bundle_after is not None
        self.assertGreater(
            bundle_after.global_totals.rules_by_year.get(2026, Decimal("0")),
            Decimal("0"),
        )

    def test_ten_rules_mask_cache_hit(self) -> None:
        from calculations.domain.services.route_effects_loader import (
            fetch_routes_dataframe_cached_timed,
        )
        from calculations.domain.services.scenario_effects_compute import (
            compute_kpi_totals,
            rule_specs_from_context,
        )
        from calculations.domain.services.route_mart_store import (
            load_mart_meta,
            load_mart_sidecar_dataframe,
            resolve_mart_parquet_path,
        )
        import shutil
        from calculations.domain.services.scenario_compute_store import (
            scenario_compute_cache_root,
        )

        category = BTDCategory.objects.create(name="BTD10", scenario=self.scenario, position=1)
        for year, coef in [(2025, "1"), (2026, "1.1")]:
            BTDCategoryValue.objects.create(
                scenario=self.scenario,
                category=category,
                year=year,
                value=Decimal(coef),
            )
        self.route.freight_charge_rub = Decimal("1000000.00")
        self.route.save(update_fields=["freight_charge_rub"])
        fetch_routes_dataframe_cached_timed(self.route_set.id)

        service = TariffRuleService()
        presets = [
            ("wagon_kind", [str(self.route.wagon_kind_id)]),
            ("cargo_group", ["1"]),
            ("message_type", [str(self.route.message_type_id)]),
            ("shipment_type", [str(self.route.shipment_type_id)]),
            ("origin_railroad", ["01"]),
            ("shipper_holding", ["Прочие"]),
            ("distance_belt", 500),
            (None, None),
        ]
        for index, (parameter, values) in enumerate(presets):
            conditions = []
            if parameter:
                operator = (
                    "lt"
                    if parameter == "distance_belt" and isinstance(values, int)
                    else "include"
                )
                conditions.append(
                    {
                        "parameter": parameter,
                        "operator": operator,
                        "values": values,
                    },
                )
            dto = CreateTariffRuleDTO(
                scenario_id=self.scenario.id,
                name=f"BENCH-test-{index}",
                base_percent="100",
                position=index + 1,
                conditions=conditions,
                year_values={"2026": "1.0500"},
            )
            with self.captureOnCommitCallbacks(execute=True):
                service.create_rule(dto, self.user)

        scenario = Scenario.objects.select_related("route_set").get(pk=self.scenario.pk)
        context = self.service.build_scenario_context(scenario)
        rule_specs = rule_specs_from_context(self.service, context)
        parquet = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
        df, _ = load_mart_sidecar_dataframe(parquet, include_charge=True)
        meta = load_mart_meta(parquet)

        _totals1, timings1 = compute_kpi_totals(
            df,
            years=context.years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=meta,
        )
        self.assertGreater(timings1.get("masks_ms", 0), 0)

        shutil.rmtree(scenario_compute_cache_root(), ignore_errors=True)
        _totals2, timings2 = compute_kpi_totals(
            df,
            years=context.years,
            base_coef_by_year=context.base_coef_by_year,
            rule_specs=rule_specs,
            route_set_id=scenario.route_set_id,
            mart_meta=meta,
        )
        self.assertLessEqual(timings2.get("masks_ms", 999), 50)
