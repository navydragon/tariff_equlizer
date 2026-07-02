from django.test import SimpleTestCase

from core.domain.cargo.etsng_categories import (
    CONSUMER_GOODS_POSITIONS,
    FOOD_GOODS_POSITIONS,
    classify_cargo_flags,
    expand_etsng_position_spec,
)


class ExpandEtsngPositionSpecTests(SimpleTestCase):
    def test_expands_range(self) -> None:
        positions = expand_etsng_position_spec(["041-044"])
        self.assertEqual(positions, frozenset({"041", "042", "043", "044"}))

    def test_expands_single_position(self) -> None:
        positions = expand_etsng_position_spec(["101", "601"])
        self.assertEqual(positions, frozenset({"101", "601"}))

    def test_consumer_positions_include_expected_samples(self) -> None:
        self.assertIn("041", CONSUMER_GOODS_POSITIONS)
        self.assertIn("691", CONSUMER_GOODS_POSITIONS)
        self.assertNotIn("521", CONSUMER_GOODS_POSITIONS)

    def test_food_positions_include_expected_samples(self) -> None:
        self.assertIn("041", FOOD_GOODS_POSITIONS)
        self.assertIn("521", FOOD_GOODS_POSITIONS)
        self.assertNotIn("691", FOOD_GOODS_POSITIONS)


class ClassifyCargoFlagsTests(SimpleTestCase):
    def test_consumer_and_food_overlap_position(self) -> None:
        self.assertEqual(classify_cargo_flags("41101"), (True, True))

    def test_consumer_only_position(self) -> None:
        self.assertEqual(classify_cargo_flags("691101"), (True, False))

    def test_food_only_position(self) -> None:
        self.assertEqual(classify_cargo_flags("521101"), (False, True))

    def test_non_category_code(self) -> None:
        self.assertEqual(classify_cargo_flags("16101"), (False, False))

    def test_accepts_six_digit_etsng_code(self) -> None:
        self.assertEqual(classify_cargo_flags("041101"), (True, True))
