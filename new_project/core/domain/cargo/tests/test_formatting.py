from django.test import SimpleTestCase

from core.domain.cargo.formatting import (
    cargo_code_3_from_etsng,
    format_cargo_code_3,
    format_etsng_code,
    parse_etsng_code,
)


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


class FormatCargoCode3Tests(SimpleTestCase):
    def test_sqlite_int_pads_leading_zero(self) -> None:
        self.assertEqual(format_cargo_code_3(16), "016")

    def test_string_preserved(self) -> None:
        self.assertEqual(format_cargo_code_3("016"), "016")
        self.assertEqual(format_cargo_code_3("161"), "161")

    def test_empty(self) -> None:
        self.assertEqual(format_cargo_code_3(None), "")
        self.assertEqual(format_cargo_code_3(""), "")


class CargoCode3FromEtsngTests(SimpleTestCase):
    def test_from_int_full_code(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng(16101), "016")

    def test_from_six_digit_string(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng("016101"), "016")

    def test_from_standard_code(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng(161016), "161")
