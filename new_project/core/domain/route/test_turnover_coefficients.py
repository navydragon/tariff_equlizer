from decimal import Decimal

from django.test import SimpleTestCase

from core.domain.route.turnover_coefficients import (
    LOADING_BASE_YEAR,
    coef_for_year,
    coefs_from_row,
    coefs_to_route_kwargs,
    quantize_coef,
    route_field_for_year,
    sqlite_loading_column_for_year,
)


class TurnoverCoefficientsTests(SimpleTestCase):
    def test_sqlite_column_name_for_year(self) -> None:
        self.assertEqual(
            sqlite_loading_column_for_year(2026),
            "2026 Погрузка,т",
        )

    def test_quantize_coef_rounds_to_three_decimals(self) -> None:
        self.assertEqual(quantize_coef("1.002631652"), Decimal("1.003"))
        self.assertIsNone(quantize_coef(""))

    def test_coef_for_year_outside_range_is_one(self) -> None:
        stored = {2026: Decimal("1.050")}
        self.assertEqual(coef_for_year(stored, 2031), Decimal("1"))
        self.assertIsNone(stored.get(2030))

    def test_coefs_from_row_reads_available_columns(self) -> None:
        base = sqlite_loading_column_for_year(LOADING_BASE_YEAR)
        col_2027 = sqlite_loading_column_for_year(2027)
        row = {base: "1000", col_2027: "920"}
        coefs = coefs_from_row(row, available_columns={base, col_2027})
        self.assertEqual(coefs[2026], Decimal("1.000"))
        self.assertEqual(coefs[2027], Decimal("0.920"))

    def test_coefs_from_row_base_zero_makes_coefs_empty(self) -> None:
        base = sqlite_loading_column_for_year(LOADING_BASE_YEAR)
        col_2027 = sqlite_loading_column_for_year(2027)
        row = {base: "0", col_2027: "920"}
        coefs = coefs_from_row(row, available_columns={base, col_2027})
        self.assertIsNone(coefs[2026])
        self.assertIsNone(coefs[2027])

    def test_coefs_from_row_missing_year_column_is_none(self) -> None:
        base = sqlite_loading_column_for_year(LOADING_BASE_YEAR)
        row = {base: "1000"}
        coefs = coefs_from_row(row, available_columns={base})
        self.assertEqual(coefs[2026], Decimal("1.000"))
        self.assertIsNone(coefs[2027])

    def test_coefs_to_route_kwargs(self) -> None:
        kwargs = coefs_to_route_kwargs({2026: Decimal("1.010")})
        self.assertEqual(
            kwargs[route_field_for_year(2026)],
            Decimal("1.010"),
        )
