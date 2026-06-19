from decimal import Decimal
from pathlib import Path

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import RouteSet
from scenarios.domain.constants import PRICE_CHANGE_PARAMETER_KEYS
from scenarios.domain.services.base_btd_seed import BASE_SCENARIO_NAME
from scenarios.domain.services import (
    BTDCategoryService,
    BTDCategoryValueService,
    ExchangeRateService,
    InflationService,
    ElasticityService,
    PriceChangeSettingService,
    ScenarioService,
)
from scenarios.domain.repositories import ScenarioRepository
from scenarios.domain.dto import (
    CreateBTDCategoryDTO,
    CreateScenarioDTO,
    UpdateBTDCategoryValueDTO,
    UpdateExchangeRateValueDTO,
    UpdateInflationValueDTO,
    CreateElasticityRuleDTO,
    UpdateElasticityRuleDTO,
)
from core.domain.services.app_settings import SHARE_MODE_ALL, SHARE_MODE_OWN, SHARE_SCENARIOS_CODE
from core.models import Setting
from scenarios.models import (
    Scenario,
    BTDCategory,
    BTDCategoryValue,
    ExchangeRateSet,
    InflationSet,
    ElasticitySet,
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)


User = get_user_model()


class BTDCategoryServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="test_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS", code="RS")
        self.scenario = Scenario.objects.create(
            name="Сценарий 1",
            description="Тестовый сценарий",
            start_year=2025,
            end_year=2035,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = BTDCategoryService()

    def test_create_categories_auto_positions(self):
        """
        Создание категорий без явной позиции должно проставлять позиции по
        порядку.
        """
        dto1 = CreateBTDCategoryDTO(
            name="Категория 1",
            scenario_id=self.scenario.id,
        )
        dto2 = CreateBTDCategoryDTO(
            name="Категория 2",
            scenario_id=self.scenario.id,
        )

        cat1, errors1 = self.service.create_category(dto1, self.user)
        cat2, errors2 = self.service.create_category(dto2, self.user)

        self.assertFalse(errors1)
        self.assertFalse(errors2)
        self.assertEqual(cat1.position, 1)
        self.assertEqual(cat2.position, 2)

    def test_delete_category_shifts_positions(self):
        """После удаления категории позиции следующих должны уменьшаться на 1."""
        # Создаем три категории
        BTDCategory.objects.create(
            name="Категория 1",
            scenario=self.scenario,
            position=1,
        )
        BTDCategory.objects.create(
            name="Категория 2",
            scenario=self.scenario,
            position=2,
        )
        BTDCategory.objects.create(
            name="Категория 3",
            scenario=self.scenario,
            position=3,
        )

        cat2 = BTDCategory.objects.get(position=2)

        success, errors = self.service.delete_category(cat2.id, self.user)
        self.assertTrue(success)
        self.assertFalse(errors)

        positions = list(
            BTDCategory.objects.filter(scenario=self.scenario)
            .order_by("position")
            .values_list("name", "position")
        )
        self.assertEqual(positions, [("Категория 1", 1), ("Категория 3", 2)])


class BTDCategoryValueServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="matrix_user",
            password="matrix_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS2", code="RS2")
        self.scenario = Scenario.objects.create(
            name="Сценарий 2",
            description="Тест матрицы значений",
            start_year=2024,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.category = BTDCategory.objects.create(
            name="Индексация базовая",
            scenario=self.scenario,
            position=1,
        )
        self.service = BTDCategoryValueService()

    def test_update_value_creates_record_when_absent(self):
        """Первое обновление ячейки создает новую запись BTDCategoryValue."""
        dto = UpdateBTDCategoryValueDTO(
            scenario_id=self.scenario.id,
            category_id=self.category.id,
            year=2024,
            value="1.076",
        )
        value_dto, errors = self.service.update_value(dto, self.user)

        self.assertFalse(errors)
        self.assertIsNotNone(value_dto)
        self.assertEqual(value_dto.year, 2024)
        self.assertEqual(Decimal(value_dto.value), Decimal("1.076"))

        obj = BTDCategoryValue.objects.get(
            scenario=self.scenario,
            category=self.category,
            year=2024,
        )
        self.assertEqual(obj.value, Decimal("1.076"))

    def test_update_value_updates_existing_record(self):
        """Повторное обновление ячейки изменяет value, не создавая дублей."""
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=self.category,
            year=2025,
            value=Decimal("1.000"),
        )

        dto = UpdateBTDCategoryValueDTO(
            scenario_id=self.scenario.id,
            category_id=self.category.id,
            year=2025,
            value="1.125",
        )
        value_dto, errors = self.service.update_value(dto, self.user)

        self.assertFalse(errors)
        self.assertIsNotNone(value_dto)
        self.assertEqual(Decimal(value_dto.value), Decimal("1.125"))

        objs = BTDCategoryValue.objects.filter(
            scenario=self.scenario,
            category=self.category,
            year=2025,
        )
        self.assertEqual(objs.count(), 1)
        self.assertEqual(objs.first().value, Decimal("1.125"))

    def test_update_value_rejects_year_out_of_range(self):
        """Год вне диапазона сценария должен приводить к ошибке."""
        dto = UpdateBTDCategoryValueDTO(
            scenario_id=self.scenario.id,
            category_id=self.category.id,
            year=2030,
            value="1.01",
        )
        value_dto, errors = self.service.update_value(dto, self.user)

        self.assertIsNone(value_dto)
        self.assertTrue(errors)

    def test_get_matrix_returns_all_categories_and_years(self):
        """Матрица должна возвращать список лет и категорий с их значениями."""
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=self.category,
            year=2024,
            value=Decimal("1.050"),
        )

        payload, errors = self.service.get_matrix(self.scenario.id, self.user)

        self.assertFalse(errors)
        self.assertIn("years", payload)
        self.assertIn("categories", payload)
        self.assertIn("total_coefficient", payload)
        self.assertEqual(payload["years"], [2024, 2025, 2026])

        self.assertEqual(len(payload["categories"]), 1)
        cat = payload["categories"][0]
        self.assertEqual(cat["name"], self.category.name)
        self.assertEqual(cat["values"].get("2024"), "1.0500")

    def test_total_coefficient_calculated_for_each_year(self):
        """Итоговый коэффициент рассчитывается по алгоритму для каждого года сценария."""
        # Первая категория (позиция 1) уже создана в setUp.
        first_cat = self.category

        second_cat = BTDCategory.objects.create(
            name="Категория 2",
            scenario=self.scenario,
            position=2,
        )
        third_cat = BTDCategory.objects.create(
            name="Категория 3",
            scenario=self.scenario,
            position=3,
        )

        # Годы: 2024 (первый), 2025, 2026.
        # Значения подобраны так, чтобы коэффициенты были:
        # 2025: 2 * (20/10) * (10/5) = 8
        # 2026: 3 * (40/20) * (20/10) = 12
        BTDCategoryValue.objects.bulk_create(
            [
                # Первая категория
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=first_cat,
                    year=2024,
                    value=Decimal("1.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=first_cat,
                    year=2025,
                    value=Decimal("2.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=first_cat,
                    year=2026,
                    value=Decimal("3.0000"),
                ),
                # Вторая категория
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=second_cat,
                    year=2024,
                    value=Decimal("10.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=second_cat,
                    year=2025,
                    value=Decimal("20.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=second_cat,
                    year=2026,
                    value=Decimal("40.0000"),
                ),
                # Третья категория
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=third_cat,
                    year=2024,
                    value=Decimal("5.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=third_cat,
                    year=2025,
                    value=Decimal("10.0000"),
                ),
                BTDCategoryValue(
                    scenario=self.scenario,
                    category=third_cat,
                    year=2026,
                    value=Decimal("20.0000"),
                ),
            ]
        )

        payload, errors = self.service.get_matrix(self.scenario.id, self.user)

        self.assertFalse(errors)
        totals = payload["total_coefficient"]

        # Первый год должен быть пустым.
        self.assertEqual(totals.get("2024"), "")

        # Последующие годы — рассчитанные значения.
        self.assertEqual(Decimal(totals.get("2025")), Decimal("8.0000"))
        self.assertEqual(Decimal(totals.get("2026")), Decimal("12.0000"))

    def test_total_coefficient_empty_when_missing_or_zero_values(self):
        """При отсутствии значений или нулевом знаменателе итоговый коэффициент должен быть пустым."""
        first_cat = self.category
        second_cat = BTDCategory.objects.create(
            name="Категория 2",
            scenario=self.scenario,
            position=2,
        )

        # Первый год — базовые значения
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=first_cat,
            year=2024,
            value=Decimal("1.0000"),
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=second_cat,
            year=2024,
            value=Decimal("0.0000"),
        )

        # Во втором году у второй категории знаменатель будет 0 -> пусто
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=first_cat,
            year=2025,
            value=Decimal("2.0000"),
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=second_cat,
            year=2025,
            value=Decimal("10.0000"),
        )

        payload, errors = self.service.get_matrix(self.scenario.id, self.user)

        self.assertFalse(errors)
        totals = payload["total_coefficient"]

        # Первый год пустой по определению, второй — из-за деления на ноль.
        self.assertEqual(totals.get("2024"), "")
        self.assertEqual(totals.get("2025"), "")


class ExchangeRateServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="fx_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS3", code="RS3")
        self.scenario = Scenario.objects.create(
            name="FX scenario",
            description="",
            start_year=2025,
            end_year=2027,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = ExchangeRateService()

    def test_create_set_and_attach_and_matrix(self):
        rate_set, errors = self.service.create_set("Набор 1", self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(rate_set)

        updated, errors = self.service.attach_set_to_scenario(
            self.scenario.id, rate_set.id, self.user
        )
        self.assertFalse(errors)
        self.assertEqual(updated.exchange_rate_set_id, rate_set.id)

        payload, errors = self.service.get_matrix(self.scenario.id, self.user)
        self.assertFalse(errors)
        self.assertEqual(payload["years"], [2025, 2026, 2027])
        self.assertIsNotNone(payload["rate_set"])
        self.assertEqual(payload["rate_set"].id, rate_set.id)

    def test_update_value_creates_record(self):
        rate_set_dto, _ = self.service.create_set("Набор 2", self.user)
        self.service.attach_set_to_scenario(
            self.scenario.id,
            rate_set_dto.id,
            self.user,
        )

        dto = UpdateExchangeRateValueDTO(
            scenario_id=self.scenario.id,
            rate_set_id=rate_set_dto.id,
            year=2026,
            usd_rub="90.1234",
        )
        value_dto, errors = self.service.update_value(dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(value_dto)
        self.assertEqual(Decimal(value_dto.usd_rub), Decimal("90.1234"))

    def test_delete_set_detaches_scenario(self):
        rate_set, _ = self.service.create_set("К удалению", self.user)
        self.service.attach_set_to_scenario(
            self.scenario.id,
            rate_set.id,
            self.user,
        )

        ok, errors = self.service.delete_set(rate_set.id, self.user)
        self.assertTrue(ok)
        self.assertFalse(errors)

        self.scenario.refresh_from_db()
        self.assertIsNone(self.scenario.exchange_rate_set_id)
        self.assertIsNone(self.service.set_repository.get_by_id(rate_set.id))

    def test_delete_set_denied_for_other_user(self):
        rate_set, _ = self.service.create_set("Чужой набор", self.user)
        other = User.objects.create_user(login="fx_other", password="test_pass")

        ok, errors = self.service.delete_set(rate_set.id, other)
        self.assertFalse(ok)
        self.assertIn("Нет прав", errors[0])


class InflationServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="inflation_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS4", code="RS4")
        self.scenario = Scenario.objects.create(
            name="Inflation scenario",
            description="",
            start_year=2025,
            end_year=2027,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = InflationService()

    def test_create_set_and_attach_and_matrix(self):
        inflation_set, errors = self.service.create_set("Набор 1", self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(inflation_set)

        updated, errors = self.service.attach_set_to_scenario(
            self.scenario.id, inflation_set.id, self.user
        )
        self.assertFalse(errors)
        self.assertEqual(updated.inflation_set_id, inflation_set.id)

        payload, errors = self.service.get_matrix(self.scenario.id, self.user)
        self.assertFalse(errors)
        self.assertEqual(payload["years"], [2025, 2026, 2027])
        self.assertIsNotNone(payload["inflation_set"])
        self.assertEqual(payload["inflation_set"].id, inflation_set.id)

    def test_update_value_creates_record(self):
        inflation_set_dto, _ = self.service.create_set("Набор 2", self.user)
        self.service.attach_set_to_scenario(
            self.scenario.id,
            inflation_set_dto.id,
            self.user,
        )

        dto = UpdateInflationValueDTO(
            scenario_id=self.scenario.id,
            inflation_set_id=inflation_set_dto.id,
            year=2026,
            rate_percent="4.5000",
        )
        value_dto, errors = self.service.update_value(dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(value_dto)
        self.assertEqual(Decimal(value_dto.rate_percent), Decimal("4.5000"))

    def test_delete_set_detaches_scenario(self):
        inflation_set, _ = self.service.create_set("К удалению", self.user)
        self.service.attach_set_to_scenario(
            self.scenario.id,
            inflation_set.id,
            self.user,
        )

        ok, errors = self.service.delete_set(inflation_set.id, self.user)
        self.assertTrue(ok)
        self.assertFalse(errors)

        self.scenario.refresh_from_db()
        self.assertIsNone(self.scenario.inflation_set_id)
        self.assertIsNone(self.service.set_repository.get_by_id(inflation_set.id))

    def test_delete_set_denied_for_other_user(self):
        inflation_set, _ = self.service.create_set("Чужой набор", self.user)
        other = User.objects.create_user(login="inflation_other", password="test_pass")

        ok, errors = self.service.delete_set(inflation_set.id, other)
        self.assertFalse(ok)
        self.assertIn("Нет прав", errors[0])


class PriceChangeSettingServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="price_change_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS5", code="RS5")
        self.scenario = Scenario.objects.create(
            name="Price change scenario",
            description="",
            start_year=2025,
            end_year=2027,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = PriceChangeSettingService()
        self.scenario_repository = ScenarioRepository()

    def test_empty_scenario_returns_all_fixed(self):
        settings = self.service.get_settings(self.scenario.id)
        self.assertEqual(len(settings), len(PRICE_CHANGE_PARAMETER_KEYS))
        self.assertTrue(all(mode == "fixed" for mode in settings.values()))

    def test_save_and_get_round_trip(self):
        payload = {key: "inflation" if key == "operators" else "fixed" for key in PRICE_CHANGE_PARAMETER_KEYS}
        errors = self.service.save_settings(self.scenario.id, payload, self.user)
        self.assertEqual(errors, [])

        settings = self.service.get_settings(self.scenario.id)
        self.assertEqual(settings["operators"], "inflation")
        self.assertEqual(settings["cost"], "fixed")

    def test_invalid_parameter_rejected(self):
        errors = self.service.save_settings(
            self.scenario.id,
            {"operators": "inflation", "unknown": "fixed"},
            self.user,
        )
        self.assertTrue(errors)

    def test_invalid_mode_rejected(self):
        payload = {key: "fixed" for key in PRICE_CHANGE_PARAMETER_KEYS}
        payload["operators"] = "other"
        errors = self.service.save_settings(self.scenario.id, payload, self.user)
        self.assertTrue(errors)

    def test_save_denied_for_other_user(self):
        other = User.objects.create_user(login="price_other", password="test_pass")
        payload = {key: "fixed" for key in PRICE_CHANGE_PARAMETER_KEYS}
        errors = self.service.save_settings(self.scenario.id, payload, other)
        self.assertIn("Нет прав", errors[0])

    def test_copy_scenario_copies_price_settings(self):
        payload = {key: "inflation" if key in {"cost", "market_price"} else "fixed" for key in PRICE_CHANGE_PARAMETER_KEYS}
        self.service.save_settings(self.scenario.id, payload, self.user)

        copied = self.scenario_repository.copy_scenario(
            source_id=self.scenario.id,
            new_name="Копия",
            new_author=self.user,
        )
        self.assertIsNotNone(copied)

        copied_settings = self.service.get_settings(copied.id)
        self.assertEqual(copied_settings["cost"], "inflation")
        self.assertEqual(copied_settings["operators"], "fixed")

    def test_update_scenario_via_service_saves_price_settings(self):
        scenario_service = ScenarioService()
        from scenarios.domain.dto import UpdateScenarioDTO

        payload = {key: "inflation" for key in PRICE_CHANGE_PARAMETER_KEYS}
        dto = UpdateScenarioDTO(price_change_settings=payload)
        updated, errors = scenario_service.update_scenario(self.scenario.id, dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.price_change_settings["transshipment"], "inflation")

    def test_update_scenario_saves_export_price_mode(self):
        scenario_service = ScenarioService()
        from scenarios.domain.dto import UpdateScenarioDTO

        dto = UpdateScenarioDTO(export_price_mode="by_fx")
        updated, errors = scenario_service.update_scenario(self.scenario.id, dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(updated)
        self.assertEqual(updated.export_price_mode, "by_fx")

        self.scenario.refresh_from_db()
        self.assertEqual(self.scenario.export_price_mode, "by_fx")

    def test_copy_scenario_copies_export_price_mode(self):
        self.scenario.export_price_mode = Scenario.ExportPriceMode.BY_FX
        self.scenario.save(update_fields=["export_price_mode"])

        copied = self.scenario_repository.copy_scenario(
            source_id=self.scenario.id,
            new_name="Копия экспорт",
            new_author=self.user,
        )
        self.assertIsNotNone(copied)
        self.assertEqual(copied.export_price_mode, Scenario.ExportPriceMode.BY_FX)

    def test_update_scenario_saves_consider_enterprise_load(self):
        scenario_service = ScenarioService()
        from scenarios.domain.dto import UpdateScenarioDTO

        dto = UpdateScenarioDTO(consider_enterprise_load=False)
        updated, errors = scenario_service.update_scenario(self.scenario.id, dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(updated)
        self.assertFalse(updated.consider_enterprise_load)

        self.scenario.refresh_from_db()
        self.assertFalse(self.scenario.consider_enterprise_load)

    def test_copy_scenario_copies_consider_enterprise_load(self):
        self.scenario.consider_enterprise_load = False
        self.scenario.save(update_fields=["consider_enterprise_load"])

        copied = self.scenario_repository.copy_scenario(
            source_id=self.scenario.id,
            new_name="Копия загрузки",
            new_author=self.user,
        )
        self.assertIsNotNone(copied)
        self.assertFalse(copied.consider_enterprise_load)


class ScenarioCopyTests(TestCase):
    """Копирование сценария при создании на базе выбранного."""

    def setUp(self) -> None:
        self.user = User.objects.create_user(login="copy_user", password="test_pass")
        self.route_set = RouteSet.objects.create(name="RS_COPY", code="RS_COPY")
        self.fx_set = ExchangeRateSet.objects.create(
            name="Прогноз ЦБ", author=self.user
        )
        self.inflation_set = InflationSet.objects.create(
            name="Прогноз ЦБ", author=self.user
        )
        self.scenario = Scenario.objects.create(
            name="Исходный",
            description="Описание исходного",
            start_year=2025,
            end_year=2027,
            route_set=self.route_set,
            exchange_rate_set=self.fx_set,
            inflation_set=self.inflation_set,
            author=self.user,
        )
        self.btd_category = BTDCategory.objects.create(
            name="Индексация",
            scenario=self.scenario,
            position=1,
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=self.btd_category,
            year=2025,
            value=Decimal("1.1250"),
        )
        self.tariff_rule = TariffRule.objects.create(
            scenario=self.scenario,
            name="Льгота уголь",
            base_percent=Decimal("50.0000"),
            position=1,
        )
        TariffRuleCondition.objects.create(
            tariff_rule=self.tariff_rule,
            parameter="cargo_group",
            operator="include",
            values=["Уголь"],
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=self.tariff_rule,
            year=2026,
            coefficient=Decimal("0.9500"),
        )
        PriceChangeSettingService().save_settings(
            self.scenario.id,
            {key: "inflation" if key == "operators" else "fixed" for key in PRICE_CHANGE_PARAMETER_KEYS},
            self.user,
        )
        self.repository = ScenarioRepository()
        self.scenario_service = ScenarioService()

    def test_copy_scenario_transfers_all_configurable_parameters(self) -> None:
        copied = self.repository.copy_scenario(
            source_id=self.scenario.id,
            new_name="Копия",
            new_author=self.user,
        )
        self.assertIsNotNone(copied)

        copied.refresh_from_db()
        self.assertEqual(copied.description, self.scenario.description)
        self.assertEqual(copied.start_year, self.scenario.start_year)
        self.assertEqual(copied.end_year, self.scenario.end_year)
        self.assertEqual(copied.route_set_id, self.scenario.route_set_id)
        self.assertEqual(copied.exchange_rate_set_id, self.fx_set.id)
        self.assertEqual(copied.inflation_set_id, self.inflation_set.id)

        settings = PriceChangeSettingService().get_settings(copied.id)
        self.assertEqual(settings["operators"], "inflation")
        self.assertEqual(settings["cost"], "fixed")

        copied_categories = list(
            BTDCategory.objects.filter(scenario=copied).order_by("position")
        )
        self.assertEqual(len(copied_categories), 1)
        self.assertEqual(copied_categories[0].name, "Индексация")
        self.assertNotEqual(copied_categories[0].id, self.btd_category.id)

        copied_value = BTDCategoryValue.objects.get(
            scenario=copied,
            category=copied_categories[0],
            year=2025,
        )
        self.assertEqual(copied_value.value, Decimal("1.1250"))

        copied_rules = list(
            TariffRule.objects.filter(scenario=copied).prefetch_related(
                "conditions", "year_values"
            )
        )
        self.assertEqual(len(copied_rules), 1)
        self.assertEqual(copied_rules[0].name, "Льгота уголь")
        self.assertEqual(copied_rules[0].base_percent, Decimal("50.0000"))
        self.assertNotEqual(copied_rules[0].id, self.tariff_rule.id)

        conditions = list(copied_rules[0].conditions.all())
        self.assertEqual(len(conditions), 1)
        self.assertEqual(conditions[0].parameter, "cargo_group")
        self.assertEqual(conditions[0].values, ["Уголь"])

        year_values = list(copied_rules[0].year_values.all())
        self.assertEqual(len(year_values), 1)
        self.assertEqual(year_values[0].year, 2026)
        self.assertEqual(year_values[0].coefficient, Decimal("0.9500"))

    def test_create_scenario_from_base_via_service(self) -> None:
        dto = CreateScenarioDTO(
            name="Новый сценарий",
            description="Новое описание",
            start_year=2025,
            end_year=2028,
            base_scenario_id=self.scenario.id,
        )
        created, errors = self.scenario_service.create_scenario_from_base(
            dto, self.user
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(created)
        self.assertEqual(created.name, "Новый сценарий")
        self.assertEqual(created.description, "Новое описание")
        self.assertEqual(created.end_year, 2028)
        self.assertEqual(created.exchange_rate_set_id, self.fx_set.id)
        self.assertEqual(created.inflation_set_id, self.inflation_set.id)
        self.assertEqual(created.price_change_settings["operators"], "inflation")
        self.assertEqual(
            BTDCategory.objects.filter(scenario_id=created.id).count(), 1
        )
        self.assertEqual(
            TariffRule.objects.filter(scenario_id=created.id).count(), 1
        )


class ShareScenariosAccessTests(TestCase):
    def setUp(self) -> None:
        Setting.objects.filter(code=SHARE_SCENARIOS_CODE).delete()
        self.owner = User.objects.create_user(login="owner", password="pass")
        self.other = User.objects.create_user(login="other", password="pass")
        self.route_set = RouteSet.objects.create(name="RS_SHARE", code="RS_SHARE")
        self.owner_scenario = Scenario.objects.create(
            name="Owner scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.owner,
        )
        self.other_scenario = Scenario.objects.create(
            name="Other scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.other,
        )
        self.scenario_service = ScenarioService()
        self.fx_service = ExchangeRateService()
        self.inflation_service = InflationService()

    def _set_share_mode(self, mode: str) -> None:
        Setting.objects.update_or_create(
            code=SHARE_SCENARIOS_CODE,
            defaults={"description": "", "value": mode},
        )

    def test_list_scenarios_own_mode_shows_only_own(self) -> None:
        self._set_share_mode(SHARE_MODE_OWN)
        ids = {s.id for s in self.scenario_service.get_user_scenarios(self.other)}
        self.assertEqual(ids, {self.other_scenario.id})

    def test_list_scenarios_all_mode_shows_everyone(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        ids = {s.id for s in self.scenario_service.get_user_scenarios(self.other)}
        self.assertEqual(ids, {self.owner_scenario.id, self.other_scenario.id})

    def test_fx_list_sets_own_mode_hides_foreign(self) -> None:
        self._set_share_mode(SHARE_MODE_OWN)
        ExchangeRateSet.objects.create(name="Owner set", author=self.owner)
        ids = {s.id for s in self.fx_service.list_sets(self.other)}
        self.assertEqual(len(ids), 0)

    def test_fx_list_sets_all_mode_shows_foreign(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        foreign_set = ExchangeRateSet.objects.create(name="Owner set", author=self.owner)
        ids = {s.id for s in self.fx_service.list_sets(self.other)}
        self.assertIn(foreign_set.id, ids)

    def test_attach_foreign_fx_set_all_mode(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        foreign_set = ExchangeRateSet.objects.create(name="Owner set", author=self.owner)
        updated, errors = self.fx_service.attach_set_to_scenario(
            self.other_scenario.id,
            foreign_set.id,
            self.other,
        )
        self.assertFalse(errors)
        self.assertEqual(updated.exchange_rate_set_id, foreign_set.id)

    def test_attach_foreign_fx_set_own_mode_denied(self) -> None:
        self._set_share_mode(SHARE_MODE_OWN)
        foreign_set = ExchangeRateSet.objects.create(name="Owner set", author=self.owner)
        _updated, errors = self.fx_service.attach_set_to_scenario(
            self.other_scenario.id,
            foreign_set.id,
            self.other,
        )
        self.assertTrue(errors)
        self.assertIn("Нет прав", errors[0])

    def test_inflation_list_sets_all_mode_shows_foreign(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        foreign_set = InflationSet.objects.create(name="Owner infl", author=self.owner)
        ids = {s.id for s in self.inflation_service.list_sets(self.other)}
        self.assertIn(foreign_set.id, ids)

    def test_set_active_foreign_scenario_own_mode_denied(self) -> None:
        self._set_share_mode(SHARE_MODE_OWN)
        ok, errors = self.scenario_service.set_active_scenario(
            self.other,
            self.owner_scenario.id,
        )
        self.assertFalse(ok)
        self.assertTrue(errors)

    def test_set_active_foreign_scenario_all_mode_allowed(self) -> None:
        self._set_share_mode(SHARE_MODE_ALL)
        ok, errors = self.scenario_service.set_active_scenario(
            self.other,
            self.owner_scenario.id,
        )
        self.assertTrue(ok)
        self.assertFalse(errors)
        self.other.refresh_from_db()
        self.assertEqual(self.other.active_scenario_id, self.owner_scenario.id)


class LoadBaseBtdCommandTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="btd_seed_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(
            name="Технический набор",
            code="DEFAULT_ROUTE_SET",
        )
        self.scenario = Scenario.objects.create(
            name=BASE_SCENARIO_NAME,
            description="Базовый",
            start_year=2025,
            end_year=2035,
            route_set=self.route_set,
            author=self.user,
        )

    def test_load_base_btd_creates_matrix_values(self) -> None:
        call_command("load_base_btd")

        categories = list(
            BTDCategory.objects.filter(scenario=self.scenario).order_by("position")
        )
        self.assertEqual(len(categories), 5)
        self.assertEqual(categories[0].name, "Индексация базовая")

        indexation_2025 = BTDCategoryValue.objects.get(
            scenario=self.scenario,
            category=categories[0],
            year=2025,
        )
        self.assertEqual(indexation_2025.value, Decimal("1.125"))

        capital_2030 = BTDCategoryValue.objects.get(
            scenario=self.scenario,
            category=categories[1],
            year=2030,
        )
        self.assertEqual(capital_2030.value, Decimal("1.07"))

    def test_load_base_btd_missing_scenario_raises(self) -> None:
        self.scenario.delete()
        with self.assertRaises(CommandError):
            call_command("load_base_btd")


class TariffRuleOptionsApiTests(TestCase):
    def setUp(self) -> None:
        from django.test import Client
        from django.urls import reverse

        from core.models import (
            Cargo,
            CargoGroup,
            MessageType,
            RailRoad,
            Region,
            Route,
            ShipmentType,
            Station,
            WagonKind,
        )

        self.client = Client()
        self.user = User.objects.create_user(login="options_user", password="test_pass")
        self.client.force_login(self.user)
        self.route_set = RouteSet.objects.create(name="RS_OPT", code="RS_OPT")
        self.scenario = Scenario.objects.create(
            name="Options scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.reverse = reverse

        group_low, _ = CargoGroup.objects.update_or_create(
            code=1,
            defaults={"name": "Уголь каменный", "position": 1},
        )
        group_high, _ = CargoGroup.objects.update_or_create(
            code=3,
            defaults={"name": "Нефтяные грузы", "position": 3},
        )

        railroad, _ = RailRoad.objects.get_or_create(code="01", defaults={"name": "Road"})
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
        wagon_kind, _ = WagonKind.objects.get_or_create(code="WK", defaults={"name": "Wagon"})
        shipment_type, _ = ShipmentType.objects.get_or_create(code="ST", defaults={"name": "Shipment"})
        message_type, _ = MessageType.objects.get_or_create(code="MT", defaults={"name": "Message"})

        for idx, group in enumerate((group_high, group_low), start=1):
            cargo, _ = Cargo.objects.get_or_create(
                code=3000 + idx,
                defaults={"name": f"Cargo {idx}", "cargo_group": group},
            )
            Route.objects.create(
                route_set=self.route_set,
                cargo=cargo,
                origin_station=origin,
                destination_station=destination,
                wagon_kind=wagon_kind,
                shipment_type=shipment_type,
                message_type=message_type,
                route_code=f"OPT-{idx}",
            )

    def test_cargo_group_options_sorted_by_position(self) -> None:
        url = self.reverse(
            "scenarios:tariff_rule_options",
            kwargs={"scenario_id": self.scenario.id},
        )
        response = self.client.get(url, {"parameter": "cargo_group"})
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        texts = [item["text"] for item in payload["items"]]
        self.assertEqual(texts, ["Уголь каменный", "Нефтяные грузы"])


class ElasticityServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(
            login="elasticity_user",
            password="test_pass",
        )
        self.route_set = RouteSet.objects.create(name="RS_EL", code="RS_EL")
        self.scenario = Scenario.objects.create(
            name="Elasticity scenario",
            description="",
            start_year=2025,
            end_year=2027,
            route_set=self.route_set,
            author=self.user,
        )
        self.service = ElasticityService()

    def test_create_set_attach_overview_and_delete(self):
        elasticity_set, errors = self.service.create_set("Набор 1", self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(elasticity_set)

        updated, errors = self.service.attach_set_to_scenario(
            self.scenario.id,
            elasticity_set.id,
            self.user,
        )
        self.assertFalse(errors)
        self.assertEqual(updated.elasticity_set_id, elasticity_set.id)

        payload, errors = self.service.get_attached_overview(self.scenario.id, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(payload["elasticity_set"])
        self.assertEqual(payload["elasticity_set"].id, elasticity_set.id)

        ok, errors = self.service.delete_set(elasticity_set.id, self.user)
        self.assertTrue(ok)
        self.assertFalse(errors)
        self.scenario.refresh_from_db()
        self.assertIsNone(self.scenario.elasticity_set_id)

    def test_create_rule_with_points(self):
        elasticity_set, _ = self.service.create_set("Набор 2", self.user)
        dto = CreateElasticityRuleDTO(
            elasticity_set_id=elasticity_set.id,
            name="Уголь экспорт",
            position=1,
            points=[
                {"marginality": "-0.02", "coefficient": "1"},
                {"marginality": "0.13", "coefficient": "0.87"},
            ],
        )
        rule, errors = self.service.create_rule(dto, self.user)
        self.assertFalse(errors)
        self.assertIsNotNone(rule)
        self.assertEqual(rule.points_count, 2)
        self.assertEqual(rule.points[0].marginality, "-0.0200")

    def test_duplicate_marginality_rejected(self):
        elasticity_set, _ = self.service.create_set("Набор 3", self.user)
        dto = CreateElasticityRuleDTO(
            elasticity_set_id=elasticity_set.id,
            name="Дубликаты",
            points=[
                {"marginality": "0.1", "coefficient": "1"},
                {"marginality": "0.1", "coefficient": "0.9"},
            ],
        )
        rule, errors = self.service.create_rule(dto, self.user)
        self.assertIsNone(rule)
        self.assertTrue(any("Дублирующаяся" in err for err in errors))

    def test_update_rule_replaces_points(self):
        elasticity_set, _ = self.service.create_set("Набор 4", self.user)
        created, _ = self.service.create_rule(
            CreateElasticityRuleDTO(
                elasticity_set_id=elasticity_set.id,
                name="Правило",
                points=[{"marginality": "0", "coefficient": "1"}],
            ),
            self.user,
        )
        updated, errors = self.service.update_rule(
            created.id,
            UpdateElasticityRuleDTO(
                name="Правило 2",
                points=[{"marginality": "0.5", "coefficient": "1.2"}],
            ),
            self.user,
        )
        self.assertFalse(errors)
        self.assertEqual(updated.name, "Правило 2")
        self.assertEqual(len(updated.points), 1)
        self.assertEqual(updated.points[0].coefficient, "1.2000")


class ElasticityMatchingTests(TestCase):
    def setUp(self) -> None:
        from core.models import (
            Cargo,
            CargoGroup,
            MessageType,
            RailRoad,
            Region,
            Route,
            ShipmentType,
            Station,
            WagonKind,
        )
        from scenarios.domain.utils.elasticity_matching import select_rule_for_route
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet

        self.select_rule_for_route = select_rule_for_route

        self.user = User.objects.create_user(login="match_user", password="test_pass")
        self.route_set = RouteSet.objects.create(name="RS_MATCH", code="RS_MATCH")
        group, _ = CargoGroup.objects.update_or_create(
            code=1,
            defaults={"name": "Уголь каменный", "position": 1},
        )
        self.cargo, _ = Cargo.objects.get_or_create(
            code="16111",
            defaults={"name": "УГОЛЬ Г", "cargo_group": group},
        )
        railroad, _ = RailRoad.objects.get_or_create(code="DVS", defaults={"name": "ДВС"})
        region, _ = Region.objects.get_or_create(
            short_name="R",
            full_name="Region",
            type="область",
        )
        station, _ = Station.objects.get_or_create(
            esr_code=300001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(code="PV", defaults={"name": "полувагон"})
        shipment_type, _ = ShipmentType.objects.get_or_create(code="E", defaults={"name": "Экспорт"})
        self.message_type, _ = MessageType.objects.get_or_create(
            code="EXP",
            defaults={"name": "Экспорт"},
        )
        self.route = Route.objects.create(
            route_set=self.route_set,
            cargo=self.cargo,
            origin_station=station,
            destination_station=station,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=self.message_type,
            route_code="MATCH-1",
        )

        elasticity_set = ElasticitySet.objects.create(name="Match set", author=self.user)
        self.fallback = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Fallback",
            position=0,
        )
        self.specific = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Specific",
            position=1,
            cargo_group=group,
            cargo=self.cargo,
            message_type=self.message_type,
        )
        ElasticityRulePoint.objects.create(
            rule=self.fallback,
            marginality=Decimal("0"),
            coefficient=Decimal("1"),
        )
        ElasticityRulePoint.objects.create(
            rule=self.specific,
            marginality=Decimal("0"),
            coefficient=Decimal("1.1"),
        )
        self.rules = [self.fallback, self.specific]

    def test_selects_most_specific_rule(self):
        selected = self.select_rule_for_route(self.route, self.rules)
        self.assertEqual(selected.id, self.specific.id)


class ElasticityPointLookupTests(TestCase):
    def setUp(self) -> None:
        from scenarios.domain.repositories.elasticity import ElasticityRulePointRepository
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet

        self.repo = ElasticityRulePointRepository()
        self.user = User.objects.create_user(login="lookup_user", password="test_pass")
        elasticity_set = ElasticitySet.objects.create(name="Lookup set", author=self.user)
        self.rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Curve",
            position=0,
        )
        for marginality, coefficient in (
            (Decimal("-0.10"), Decimal("1.00")),
            (Decimal("0.00"), Decimal("0.90")),
            (Decimal("0.10"), Decimal("0.80")),
        ):
            ElasticityRulePoint.objects.create(
                rule=self.rule,
                marginality=marginality,
                coefficient=coefficient,
            )

    def test_get_by_marginality_exact(self):
        point = self.repo.get_by_marginality(self.rule.id, Decimal("0.00"))
        self.assertIsNotNone(point)
        self.assertEqual(point.coefficient, Decimal("0.90"))

    def test_find_floor_and_ceiling_points(self):
        floor = self.repo.find_floor_point(self.rule.id, Decimal("0.05"))
        ceiling = self.repo.find_ceiling_point(self.rule.id, Decimal("0.05"))
        self.assertEqual(floor.marginality, Decimal("0.00"))
        self.assertEqual(ceiling.marginality, Decimal("0.10"))


class RetentionCoefficientLookupTests(TestCase):
    def setUp(self) -> None:
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
        from scenarios.domain.utils.elasticity_matching import (
            lookup_coefficient_for_marginality,
            resolve_retention_coefficient,
        )
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet, Scenario

        self.lookup_coefficient_for_marginality = lookup_coefficient_for_marginality
        self.resolve_retention_coefficient = resolve_retention_coefficient

        self.user = User.objects.create_user(login="retention_user", password="test_pass")
        route_set = RouteSet.objects.create(name="Retention RS", code="RS_RET")
        self.scenario = Scenario.objects.create(
            name="Retention scenario",
            start_year=2025,
            end_year=2026,
            route_set=route_set,
            author=self.user,
        )
        self.elasticity_set = ElasticitySet.objects.create(
            name="Retention set",
            author=self.user,
        )
        self.scenario.elasticity_set = self.elasticity_set
        self.scenario.save(update_fields=["elasticity_set"])

        cargo_group = CargoGroup.objects.create(code=901, name="Retention group", position=1)
        cargo = Cargo.objects.create(code=9001, name="Retention cargo", cargo_group=cargo_group)
        railroad = RailRoad.objects.create(code="RR_RET", name="Retention road")
        region = Region.objects.create(
            short_name="RR",
            full_name="Retention region",
            type="область",
        )
        station = Station.objects.create(
            esr_code=900001,
            short_name="RET",
            full_name="Retention station",
            region=region,
            railroad=railroad,
        )
        wagon_kind = WagonKind.objects.create(code="WK_RET", name="Retention wagon")
        shipment_type = ShipmentType.objects.create(code="ST_RET", name="Retention shipment")
        message_type = MessageType.objects.create(code="MT_RET", name="Внутр. перевозки")
        self.route = Route.objects.create(
            route_set=route_set,
            cargo=cargo,
            origin_station=station,
            destination_station=station,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="RET-001",
        )
        self.rule = ElasticityRule.objects.create(
            elasticity_set=self.elasticity_set,
            name="Internal retention",
            position=0,
            message_type=message_type,
        )
        for marginality, coefficient in (
            (Decimal("-0.10"), Decimal("1.0000")),
            (Decimal("0.00"), Decimal("0.9000")),
            (Decimal("0.10"), Decimal("0.8000")),
        ):
            ElasticityRulePoint.objects.create(
                rule=self.rule,
                marginality=marginality,
                coefficient=coefficient,
            )

    def test_lookup_coefficient_uses_floor_point(self) -> None:
        coefficient = self.lookup_coefficient_for_marginality(
            self.rule,
            Decimal("0.075"),
        )
        self.assertEqual(coefficient, Decimal("0.9000"))

    def test_resolve_retention_coefficient_for_route(self) -> None:
        coefficient = self.resolve_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("0.12"),
        )
        self.assertEqual(coefficient, Decimal("0.8000"))

    def test_resolve_retention_coefficient_without_set(self) -> None:
        self.scenario.elasticity_set = None
        self.scenario.save(update_fields=["elasticity_set"])
        coefficient = self.resolve_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("0.05"),
        )
        self.assertIsNone(coefficient)

    def test_resolve_retention_coefficient_below_curve(self) -> None:
        coefficient = self.resolve_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("-0.20"),
        )
        self.assertEqual(coefficient, Decimal("1.0000"))

    def test_resolve_retention_coefficient_below_ipem_minimum(self) -> None:
        coefficient = self.resolve_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("-0.0621"),
        )
        self.assertEqual(coefficient, Decimal("1.0000"))

    def test_marginality_ratio_from_percent_matches_ipem_curve(self) -> None:
        from scenarios.domain.utils.elasticity_matching import (
            marginality_ratio_from_percent,
            resolve_retention_coefficient,
        )
        from scenarios.models import ElasticityRulePoint

        ElasticityRulePoint.objects.create(
            rule=self.rule,
            marginality=Decimal("0.13"),
            coefficient=Decimal("1.0550"),
        )
        coefficient = resolve_retention_coefficient(
            self.route,
            self.scenario,
            marginality_ratio_from_percent(Decimal("13.00")),
        )
        self.assertEqual(coefficient, Decimal("1.0550"))


class RetentionCoefficientModeTests(TestCase):
    def setUp(self) -> None:
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
        from scenarios.domain.utils.elasticity_matching import (
            compute_retention_coefficient,
            route_base_marginality_ratio,
        )
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet, Scenario

        self.compute_retention_coefficient = compute_retention_coefficient
        self.route_base_marginality_ratio = route_base_marginality_ratio

        self.user = User.objects.create_user(
            login="retention_mode_user",
            password="test_pass",
        )
        route_set = RouteSet.objects.create(name="Retention mode RS", code="RS_RMODE")
        self.scenario = Scenario.objects.create(
            name="Retention mode scenario",
            start_year=2025,
            end_year=2026,
            route_set=route_set,
            author=self.user,
        )
        elasticity_set = ElasticitySet.objects.create(
            name="Retention mode set",
            author=self.user,
        )
        self.scenario.elasticity_set = elasticity_set
        self.scenario.save(update_fields=["elasticity_set"])

        cargo_group = CargoGroup.objects.create(
            code=902,
            name="Retention mode group",
            position=1,
        )
        cargo = Cargo.objects.create(
            code=9002,
            name="Retention mode cargo",
            cargo_group=cargo_group,
        )
        railroad = RailRoad.objects.create(code="RR_RMODE", name="Retention mode road")
        region = Region.objects.create(
            short_name="RM",
            full_name="Retention mode region",
            type="область",
        )
        station = Station.objects.create(
            esr_code=900002,
            short_name="RMD",
            full_name="Retention mode station",
            region=region,
            railroad=railroad,
        )
        wagon_kind = WagonKind.objects.create(code="WK_RMODE", name="Retention mode wagon")
        shipment_type = ShipmentType.objects.create(
            code="ST_RMODE",
            name="Retention mode shipment",
        )
        message_type = MessageType.objects.create(
            code="MT_RMODE",
            name="Внутр. перевозки mode",
        )
        self.route = Route.objects.create(
            route_set=route_set,
            cargo=cargo,
            origin_station=station,
            destination_station=station,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="RMOD-001",
            market_price_per_ton=Decimal("2000"),
            production_cost_per_ton=Decimal("500"),
            rzd_cost_total_per_ton=Decimal("1000"),
            operators_cost_per_ton=Decimal("100"),
            transshipment_cost_per_ton=Decimal("50"),
        )
        self.rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="Retention mode rule",
            position=0,
            message_type=message_type,
        )
        for marginality, coefficient in (
            (Decimal("-0.10"), Decimal("1.0000")),
            (Decimal("0.00"), Decimal("0.9000")),
            (Decimal("0.10"), Decimal("0.8000")),
            (Decimal("0.20"), Decimal("0.7000")),
        ):
            ElasticityRulePoint.objects.create(
                rule=self.rule,
                marginality=marginality,
                coefficient=coefficient,
            )

    def test_route_base_marginality_ratio_from_db_fields(self) -> None:
        ratio = self.route_base_marginality_ratio(self.route)
        self.assertEqual(ratio, Decimal("0.175"))

    def test_compute_retention_coefficient_absolute_mode(self) -> None:
        from scenarios.models import Scenario

        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.ABSOLUTE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])

        coefficient = self.compute_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("0.175"),
        )
        self.assertEqual(coefficient, Decimal("0.8000"))

    def test_compute_retention_coefficient_relative_mode_unchanged_margin(self) -> None:
        from scenarios.models import Scenario

        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.RELATIVE_TO_BASE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])

        base_ratio = self.route_base_marginality_ratio(self.route)
        coefficient = self.compute_retention_coefficient(
            self.route,
            self.scenario,
            base_ratio,
        )
        self.assertEqual(coefficient, Decimal("1"))

    def test_compute_retention_coefficient_relative_mode_margin_drop(self) -> None:
        from scenarios.models import Scenario

        self.scenario.retention_coefficient_mode = (
            Scenario.RetentionCoefficientMode.RELATIVE_TO_BASE
        )
        self.scenario.save(update_fields=["retention_coefficient_mode"])

        coefficient = self.compute_retention_coefficient(
            self.route,
            self.scenario,
            Decimal("0.05"),
        )
        self.assertEqual(coefficient, Decimal("1.1"))


class EnterpriseLoadCapTests(TestCase):
    def test_apply_enterprise_load_cap_limits_growth(self) -> None:
        from scenarios.domain.utils.elasticity_matching import apply_enterprise_load_cap

        self.assertEqual(
            apply_enterprise_load_cap(
                Decimal("1.2"),
                Decimal("0.9"),
                enabled=True,
            ),
            Decimal("1.1"),
        )

    def test_apply_enterprise_load_cap_at_full_load(self) -> None:
        from scenarios.domain.utils.elasticity_matching import apply_enterprise_load_cap

        self.assertEqual(
            apply_enterprise_load_cap(
                Decimal("1.2"),
                Decimal("1"),
                enabled=True,
            ),
            Decimal("1"),
        )

    def test_apply_enterprise_load_cap_disabled(self) -> None:
        from scenarios.domain.utils.elasticity_matching import apply_enterprise_load_cap

        self.assertEqual(
            apply_enterprise_load_cap(
                Decimal("1.2"),
                Decimal("0.9"),
                enabled=False,
            ),
            Decimal("1.2"),
        )

    def test_apply_enterprise_load_cap_skips_zero_load(self) -> None:
        from scenarios.domain.utils.elasticity_matching import apply_enterprise_load_cap

        self.assertEqual(
            apply_enterprise_load_cap(
                Decimal("1.2"),
                Decimal("0"),
                enabled=True,
            ),
            Decimal("1.2"),
        )

    def test_resolve_enterprise_load_coefficient_prefers_own_value(self) -> None:
        from types import SimpleNamespace

        from scenarios.domain.utils.elasticity_matching import (
            resolve_enterprise_load_coefficient,
        )

        model_route = SimpleNamespace(enterprise_load_coefficient=Decimal("0.875"))
        operational = SimpleNamespace(
            enterprise_load_coefficient=Decimal("0.9"),
            model_route=model_route,
            model_route_id=1,
        )

        self.assertEqual(
            resolve_enterprise_load_coefficient(operational),
            Decimal("0.9"),
        )

    def test_resolve_enterprise_load_coefficient_falls_back_to_model(self) -> None:
        from types import SimpleNamespace

        from scenarios.domain.utils.elasticity_matching import (
            resolve_enterprise_load_coefficient,
        )

        model_route = SimpleNamespace(enterprise_load_coefficient=Decimal("0.875"))
        operational = SimpleNamespace(
            enterprise_load_coefficient=None,
            model_route=model_route,
            model_route_id=1,
        )

        self.assertEqual(
            resolve_enterprise_load_coefficient(operational),
            Decimal("0.875"),
        )


class ElasticityCoalSeedTests(TestCase):
    def test_reuses_existing_set_by_name_and_clears_rules(self) -> None:
        from scenarios.domain.services.base_elasticity_seed import (
            ELASTICITY_SET_NAME,
            EXPORT_RULE_NAME,
            INTERNAL_RULE_NAME,
            seed_coal_elasticity_for_scenario,
        )
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet, Scenario

        user = User.objects.create_user(login="seed_user", password="test_pass")
        other_user = User.objects.create_user(login="other_user", password="test_pass")
        route_set = RouteSet.objects.create(code="RS_SEED", name="Seed RS")
        scenario = Scenario.objects.create(
            name="Seed scenario",
            description="",
            start_year=2025,
            end_year=2030,
            route_set=route_set,
            author=user,
        )
        existing_set = ElasticitySet.objects.create(
            name=ELASTICITY_SET_NAME,
            author=other_user,
        )
        stale_rule = ElasticityRule.objects.create(
            elasticity_set=existing_set,
            name="Старое правило",
            position=0,
        )
        ElasticityRulePoint.objects.create(
            rule=stale_rule,
            marginality=Decimal("0"),
            coefficient=Decimal("1"),
        )

        result = seed_coal_elasticity_for_scenario(
            scenario,
            attach=True,
            xlsx_path=Path("/nonexistent.xlsx"),
        )

        self.assertEqual(result.elasticity_set_id, existing_set.id)
        self.assertEqual(
            ElasticitySet.objects.filter(name=ELASTICITY_SET_NAME).count(),
            1,
        )
        rules = list(
            ElasticityRule.objects.filter(elasticity_set_id=existing_set.id).order_by(
                "position",
            ),
        )
        self.assertEqual(len(rules), 2)
        self.assertEqual(rules[0].name, EXPORT_RULE_NAME)
        self.assertEqual(rules[1].name, INTERNAL_RULE_NAME)
        self.assertFalse(
            ElasticityRule.objects.filter(name="Старое правило").exists(),
        )
        scenario.refresh_from_db()
        self.assertEqual(scenario.elasticity_set_id, existing_set.id)


class IpemCoalImportBundleTests(TestCase):
    def setUp(self) -> None:
        from core.models import (
            Cargo,
            CargoGroup,
            MessageType,
            RailRoad,
            Region,
            Route,
            ShipmentType,
            Station,
            WagonKind,
        )
        from scenarios.domain.services.base_elasticity_seed import (
            EXPORT_RULE_NAME,
            INTERNAL_RULE_NAME,
        )
        from scenarios.models import ElasticityRule, ElasticitySet, Scenario

        self.user = User.objects.create_user(login="bundle_user", password="test_pass")
        self.route_set = RouteSet.objects.create(code="RS_BUNDLE", name="Bundle RS")
        self.scenario = Scenario.objects.create(
            name="Bundle scenario",
            description="",
            start_year=2025,
            end_year=2030,
            route_set=self.route_set,
            author=self.user,
        )
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
        self.station = Station.objects.create(
            esr_code=91720,
            short_name="A",
            full_name="Station A",
            region=region,
            railroad=railroad,
        )
        self.wagon_kind = WagonKind.objects.create(code="WK_PV", name="Полувагоны")
        self.shipment_type = ShipmentType.objects.create(
            code="ST_M",
            name="маршрутная",
        )
        self.message_export = MessageType.objects.create(code="MT_EXP", name="Экспорт")
        self.message_internal = MessageType.objects.create(
            code="MT_INT",
            name="Внутр. перевозки",
        )
        self.message_other = MessageType.objects.create(code="MT_OTH", name="Транзит")

        elasticity_set = ElasticitySet.objects.create(
            name="Bundle elasticity",
            author=self.user,
        )
        self.scenario.elasticity_set = elasticity_set
        self.scenario.save(update_fields=["elasticity_set"])

        self.export_rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name=EXPORT_RULE_NAME,
            position=0,
            message_type=self.message_export,
        )
        self.internal_rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name=INTERNAL_RULE_NAME,
            position=1,
            message_type=self.message_internal,
        )

        self.Route = Route

    def _create_model_route(self, route_code: str, message_type):
        return self.Route.objects.create(
            route_set=self.route_set,
            is_model=True,
            route_code=route_code,
            cargo=self.cargo,
            origin_station=self.station,
            destination_station=self.station,
            wagon_kind=self.wagon_kind,
            shipment_type=self.shipment_type,
            message_type=message_type,
        )

    def test_validate_matching_export_and_internal(self) -> None:
        from scenarios.domain.services.ipem_coal_import import (
            validate_model_route_elasticity_matching,
        )

        self._create_model_route("EXP-1", self.message_export)
        self._create_model_route("INT-1", self.message_internal)

        stats = validate_model_route_elasticity_matching(
            self.route_set,
            self.scenario,
        )
        self.assertEqual(stats.export_matched, 1)
        self.assertEqual(stats.internal_matched, 1)
        self.assertEqual(stats.unmatched_route_codes, [])

    def test_validate_matching_reports_unmatched(self) -> None:
        from scenarios.domain.services.ipem_coal_import import (
            validate_model_route_elasticity_matching,
        )

        self._create_model_route("OTHER-1", self.message_other)

        stats = validate_model_route_elasticity_matching(
            self.route_set,
            self.scenario,
        )
        self.assertEqual(stats.export_matched, 0)
        self.assertEqual(stats.internal_matched, 0)
        self.assertEqual(stats.unmatched_route_codes, ["OTHER-1"])

    def test_resolve_elasticity_rule_for_route(self) -> None:
        from scenarios.domain.services.ipem_coal_import import (
            resolve_elasticity_rule_for_route,
        )

        route = self._create_model_route("EXP-2", self.message_export)
        rule = resolve_elasticity_rule_for_route(route, self.scenario)
        self.assertIsNotNone(rule)
        self.assertEqual(rule.id, self.export_rule.id)

    def test_bundle_dry_run_does_not_attach_elasticity_set(self) -> None:
        from pathlib import Path

        from scenarios.models import Scenario

        xlsx_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "ipem"
            / "Уголь_эластика_2026.xlsx"
        )
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        scenario = Scenario.objects.create(
            name="Dry run bundle",
            description="",
            start_year=2025,
            end_year=2030,
            route_set=self.route_set,
            author=self.user,
        )
        self.assertIsNone(scenario.elasticity_set_id)

        call_command(
            "import_ipem_coal_2026_routes",
            "--file",
            str(xlsx_path),
            "--route-set-code",
            "RS_BUNDLE",
            "--scenario-id",
            str(scenario.id),
            "--dry-run",
        )
        scenario.refresh_from_db()
        self.assertIsNone(scenario.elasticity_set_id)

    def test_skip_elasticity_does_not_touch_scenario(self) -> None:
        from pathlib import Path

        from scenarios.models import Scenario

        xlsx_path = (
            Path(__file__).resolve().parents[2]
            / "data"
            / "ipem"
            / "Уголь_эластика_2026.xlsx"
        )
        if not xlsx_path.exists():
            self.skipTest(f"Файл IPEM не найден: {xlsx_path}")

        scenario = Scenario.objects.create(
            name="Skip elasticity",
            description="",
            start_year=2025,
            end_year=2030,
            route_set=self.route_set,
            author=self.user,
        )

        call_command(
            "import_ipem_coal_2026_routes",
            "--file",
            str(xlsx_path),
            "--route-set-code",
            "RS_BUNDLE",
            "--scenario-id",
            str(scenario.id),
            "--skip-elasticity",
            "--dry-run",
        )
        scenario.refresh_from_db()
        self.assertIsNone(scenario.elasticity_set_id)


class ScenarioCopyElasticityTests(TestCase):
    def test_copy_scenario_keeps_elasticity_set(self):
        user = User.objects.create_user(login="copy_user", password="test_pass")
        route_set = RouteSet.objects.create(name="RS_COPY", code="RS_COPY")
        elasticity_set = ElasticitySet.objects.create(name="Copy set", author=user)
        source = Scenario.objects.create(
            name="Source",
            description="",
            start_year=2025,
            end_year=2030,
            route_set=route_set,
            author=user,
            elasticity_set=elasticity_set,
        )
        copied = ScenarioRepository().copy_scenario(
            source.id,
            "Copied",
            user,
        )
        self.assertIsNotNone(copied)
        self.assertEqual(copied.elasticity_set_id, elasticity_set.id)
