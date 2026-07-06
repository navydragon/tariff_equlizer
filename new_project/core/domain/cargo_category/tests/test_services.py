from django.test import TestCase

from core.domain.cargo.etsng_categories import (
    classify_cargo_flags,
    clear_cargo_category_positions_cache,
    expand_etsng_position_spec,
    get_consumer_goods_positions,
    get_food_goods_positions,
)
from core.domain.cargo_category.dto import AddPositionDTO
from core.domain.cargo_category.services import CargoCategoryService
from core.models import Cargo, CargoCategoryPosition


class ExpandEtsngPositionSpecTests(TestCase):
    def test_expands_range(self) -> None:
        positions = expand_etsng_position_spec(["041-044"])
        self.assertEqual(positions, frozenset({"041", "042", "043", "044"}))

    def test_expands_single_position(self) -> None:
        positions = expand_etsng_position_spec(["101", "601"])
        self.assertEqual(positions, frozenset({"101", "601"}))


class ClassifyCargoFlagsTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        CargoCategoryPosition.objects.all().delete()
        CargoCategoryPosition.objects.bulk_create(
            [
                CargoCategoryPosition(
                    category=CargoCategoryPosition.Category.CONSUMER_GOODS,
                    position=position,
                )
                for position in ("041", "691")
            ]
            + [
                CargoCategoryPosition(
                    category=CargoCategoryPosition.Category.FOOD_GOODS,
                    position=position,
                )
                for position in ("041", "521")
            ]
        )

    def setUp(self) -> None:
        clear_cargo_category_positions_cache()

    def test_consumer_and_food_overlap_position(self) -> None:
        self.assertEqual(classify_cargo_flags("04101"), (True, True))

    def test_consumer_only_position(self) -> None:
        self.assertEqual(classify_cargo_flags("69101"), (True, False))

    def test_food_only_position(self) -> None:
        self.assertEqual(classify_cargo_flags("52101"), (False, True))

    def test_non_category_code(self) -> None:
        self.assertEqual(classify_cargo_flags("16101"), (False, False))

    def test_locomotive_on_own_axles_not_consumer(self) -> None:
        self.assertEqual(classify_cargo_flags("42201"), (False, False))

    def test_six_digit_input_normalizes_before_classify(self) -> None:
        self.assertEqual(classify_cargo_flags("041101"), (False, False))
        self.assertEqual(classify_cargo_flags("016101"), (False, False))

    def test_positions_loaded_from_db(self) -> None:
        self.assertEqual(get_consumer_goods_positions(), frozenset({"041", "691"}))
        self.assertEqual(get_food_goods_positions(), frozenset({"041", "521"}))


class CargoCategoryServiceTests(TestCase):
    @classmethod
    def setUpTestData(cls) -> None:
        CargoCategoryPosition.objects.all().delete()

    def setUp(self) -> None:
        clear_cargo_category_positions_cache()
        Cargo.objects.create(code="77701", name="Тестовый груз 777")
        Cargo.objects.create(code="16101", name="Прочий груз")

    def test_add_food_position_reclassifies_cargos(self) -> None:
        service = CargoCategoryService()
        item, errors = service.add_position(
            AddPositionDTO(
                category=CargoCategoryPosition.Category.FOOD_GOODS,
                position="777",
            )
        )

        self.assertEqual(errors, [])
        self.assertIsNotNone(item)
        cargo = Cargo.objects.get(code="77701")
        self.assertTrue(cargo.is_food_goods)
        self.assertFalse(cargo.is_consumer_goods)

    def test_delete_food_position_clears_flags(self) -> None:
        CargoCategoryPosition.objects.create(
            category=CargoCategoryPosition.Category.FOOD_GOODS,
            position="777",
        )
        Cargo.objects.filter(code="77701").update(is_food_goods=True)
        clear_cargo_category_positions_cache()

        service = CargoCategoryService()
        deleted, errors = service.delete_position(
            category=CargoCategoryPosition.Category.FOOD_GOODS,
            position="777",
        )

        self.assertEqual(errors, [])
        self.assertTrue(deleted)
        cargo = Cargo.objects.get(code="77701")
        self.assertFalse(cargo.is_food_goods)

    def test_add_duplicate_position_returns_error(self) -> None:
        CargoCategoryPosition.objects.create(
            category=CargoCategoryPosition.Category.CONSUMER_GOODS,
            position="041",
        )
        clear_cargo_category_positions_cache()

        service = CargoCategoryService()
        _, errors = service.add_position(
            AddPositionDTO(
                category=CargoCategoryPosition.Category.CONSUMER_GOODS,
                position="041",
            )
        )
        self.assertIn("Позиция уже есть в этом наборе", errors)

    def test_normalize_short_position_on_add(self) -> None:
        service = CargoCategoryService()
        item, errors = service.add_position(
            AddPositionDTO(
                category=CargoCategoryPosition.Category.CONSUMER_GOODS,
                position="99",
            )
        )
        self.assertEqual(errors, [])
        self.assertEqual(item.position, "099")
