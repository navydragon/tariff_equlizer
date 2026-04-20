from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import TestCase

from scenarios.domain.services import BTDCategoryService, BTDCategoryValueService
from scenarios.domain.dto import CreateBTDCategoryDTO, UpdateBTDCategoryValueDTO
from scenarios.models import Scenario, BTDCategory, BTDCategoryValue


User = get_user_model()


class BTDCategoryServiceTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="test_user", password="test_pass")
        self.scenario = Scenario.objects.create(
            name="Сценарий 1",
            description="Тестовый сценарий",
            start_year=2025,
            end_year=2035,
            author=self.user,
        )
        self.service = BTDCategoryService()

    def test_create_categories_auto_positions(self):
        """Создание категорий без явной позиции должно проставлять позиции по порядку."""
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
        BTDCategory.objects.create(name="Категория 1", scenario=self.scenario, position=1)
        BTDCategory.objects.create(name="Категория 2", scenario=self.scenario, position=2)
        BTDCategory.objects.create(name="Категория 3", scenario=self.scenario, position=3)

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
        self.user = User.objects.create_user(username="matrix_user", password="matrix_pass")
        self.scenario = Scenario.objects.create(
            name="Сценарий 2",
            description="Тест матрицы значений",
            start_year=2024,
            end_year=2026,
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
        self.assertEqual(cat["values"].get("2024"), "1.050")

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
