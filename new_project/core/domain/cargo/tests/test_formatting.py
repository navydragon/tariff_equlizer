from django.test import SimpleTestCase

from core.domain.cargo.formatting import (
    cargo_code_3_from_etsng,
    cargo_code_3_from_normalized,
    cargo_code_lookup_keys,
    format_app_cargo_code,
    format_cargo_code_3,
    format_etsng_code,
    normalize_rzd_cargo_code,
    parse_etsng_code,
    resolve_route_cargo_fields,
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


class FormatAppCargoCodeTests(SimpleTestCase):
    def test_anthracite_code_five_digits(self) -> None:
        self.assertEqual(format_app_cargo_code(16101), "16101")

    def test_six_digit_rzd_normalized(self) -> None:
        self.assertEqual(format_app_cargo_code("016101"), "16101")

    def test_four_digit_padded(self) -> None:
        self.assertEqual(format_app_cargo_code("8101"), "08101")

    def test_six_digit_without_leading_zero_unchanged(self) -> None:
        self.assertEqual(format_app_cargo_code(161016), "161016")

    def test_none_and_empty(self) -> None:
        self.assertEqual(format_app_cargo_code(None), "")
        self.assertEqual(format_app_cargo_code(""), "")


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


class CargoCodeLookupKeysTests(SimpleTestCase):
    def test_includes_normalized_and_six_digit_legacy(self) -> None:
        self.assertEqual(
            set(cargo_code_lookup_keys(16101)),
            {"16101", "016101"},
        )

    def test_six_digit_code_without_leading_zero(self) -> None:
        self.assertEqual(
            cargo_code_lookup_keys("161016"),
            ["161016"],
        )


class NormalizeRzdCargoCodeTests(SimpleTestCase):
    def test_six_digit_with_leading_zero(self) -> None:
        code, warn = normalize_rzd_cargo_code("016101")
        self.assertEqual(code, "16101")
        self.assertIsNone(warn)

    def test_four_digit_adds_leading_zero(self) -> None:
        code, warn = normalize_rzd_cargo_code("8101")
        self.assertEqual(code, "08101")
        self.assertIsNone(warn)

    def test_five_digit_unchanged(self) -> None:
        code, warn = normalize_rzd_cargo_code("16101")
        self.assertEqual(code, "16101")
        self.assertIsNone(warn)

    def test_six_digit_without_leading_zero_warns(self) -> None:
        code, warn = normalize_rzd_cargo_code("161016")
        self.assertEqual(code, "161016")
        self.assertIn("без ведущего нуля", warn or "")


class CargoCode3FromNormalizedTests(SimpleTestCase):
    def test_from_five_digit_code(self) -> None:
        self.assertEqual(cargo_code_3_from_normalized("16101"), "161")

    def test_from_four_digit_raw(self) -> None:
        self.assertEqual(cargo_code_3_from_normalized("8101"), "081")


class ResolveRouteCargoFieldsTests(SimpleTestCase):
    def test_main_and_izpod_normalized(self) -> None:
        fields = resolve_route_cargo_fields("016101", "8101")
        self.assertEqual(fields.main_code, "16101")
        self.assertEqual(fields.izpod_code, "08101")
        self.assertEqual(fields.code_3, "161")
        self.assertEqual(fields.izpod_3, "081")
        self.assertEqual(fields.warnings, ())

    def test_empty_izpod(self) -> None:
        fields = resolve_route_cargo_fields("016101", None)
        self.assertEqual(fields.izpod_code, "")
        self.assertEqual(fields.izpod_3, "")


class CargoCode3FromEtsngTests(SimpleTestCase):
    def test_from_int_full_code(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng(16101), "016")

    def test_from_six_digit_string(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng("016101"), "016")

    def test_from_standard_code(self) -> None:
        self.assertEqual(cargo_code_3_from_etsng(161016), "161")
