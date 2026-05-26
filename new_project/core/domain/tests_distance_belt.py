from django.test import SimpleTestCase

from core.domain.distance_belt import parse_distance_belt_midpoint


class ParseDistanceBeltMidpointTests(SimpleTestCase):
    def test_valid_belt(self) -> None:
        self.assertEqual(parse_distance_belt_midpoint("500-1000"), 750)

    def test_empty_belt(self) -> None:
        self.assertIsNone(parse_distance_belt_midpoint(""))
        self.assertIsNone(parse_distance_belt_midpoint(None))

    def test_invalid_belt(self) -> None:
        self.assertIsNone(parse_distance_belt_midpoint("abc"))
        self.assertIsNone(parse_distance_belt_midpoint("500"))
