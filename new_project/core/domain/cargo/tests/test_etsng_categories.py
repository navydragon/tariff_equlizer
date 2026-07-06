from django.test import SimpleTestCase

from core.domain.cargo.etsng_categories import expand_etsng_position_spec


class ExpandEtsngPositionSpecUnitTests(SimpleTestCase):
    def test_expands_range(self) -> None:
        positions = expand_etsng_position_spec(["041-044"])
        self.assertEqual(positions, frozenset({"041", "042", "043", "044"}))

    def test_expands_single_position(self) -> None:
        positions = expand_etsng_position_spec(["101", "601"])
        self.assertEqual(positions, frozenset({"101", "601"}))
