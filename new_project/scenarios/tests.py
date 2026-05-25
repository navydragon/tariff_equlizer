from decimal import Decimal

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
)
from core.domain.services.app_settings import SHARE_MODE_ALL, SHARE_MODE_OWN, SHARE_SCENARIOS_CODE
from core.models import Setting
from scenarios.models import (
    Scenario,
    BTDCategory,
    BTDCategoryValue,
    ExchangeRateSet,
    InflationSet,
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
