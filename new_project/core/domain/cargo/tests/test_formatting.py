from django.test import SimpleTestCase

from core.domain.cargo.formatting import format_etsng_code, parse_etsng_code


class ParseEtsngCodeTests(SimpleTestCase):
    def test_preserves_leading_zeros_from_rzd(self) -> None:
        self.assertEqual(parse_etsng_code("016101"), "016101")

    def test_preserves_six_digit_code(self) -> None:
        self.assertEqual(parse_etsng_code("010101"), "010101")

    def test_strips_whitespace(self) -> None:
        self.assertEqual(parse_etsng_code(" 016101 "), "016101")

    def test_invalid_values(self) -> None:
        self.assertIsNone(parse_etsng_code(None))
        self.assertIsNone(parse_etsng_code(""))
        self.assertIsNone(parse_etsng_code("ABC"))


class FormatEtsngCodeTests(SimpleTestCase):
    def test_anthracite_code_pads_leading_zero(self) -> None:
        self.assertEqual(format_etsng_code(16101), "016101")

    def test_stored_rzd_code_unchanged(self) -> None:
        self.assertEqual(format_etsng_code("016101"), "016101")

    def test_six_digit_code_unchanged(self) -> None:
        self.assertEqual(format_etsng_code(161016), "161016")

    def test_short_code_pads_to_six_digits(self) -> None:
        self.assertEqual(format_etsng_code(1001), "001001")

    def test_none_and_empty(self) -> None:
        self.assertEqual(format_etsng_code(None), "")
        self.assertEqual(format_etsng_code(""), "")
