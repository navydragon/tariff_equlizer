from decimal import Decimal

from django.test import SimpleTestCase

from core.domain.route.turnover_coefficients import (
    coef_for_year,
    coefs_from_row,
    coefs_to_route_kwargs,
    quantize_coef,
    route_field_for_year,
    sqlite_column_for_year,
)


class TurnoverCoefficientsTests(SimpleTestCase):
    def test_sqlite_column_name_for_year(self) -> None:
        self.assertEqual(sqlite_column_for_year(2025), "2025_% L год\\год")

    def test_quantize_coef_rounds_to_three_decimals(self) -> None:
        self.assertEqual(quantize_coef("1.002631652"), Decimal("1.003"))
        self.assertIsNone(quantize_coef(""))

    def test_coef_for_year_outside_range_is_one(self) -> None:
        stored = {2025: Decimal("1.050")}
        self.assertEqual(coef_for_year(stored, 2031), Decimal("1"))
        self.assertIsNone(stored.get(2030))

    def test_coefs_from_row_reads_available_columns(self) -> None:
        column = sqlite_column_for_year(2026)
        row = {column: "0.912"}
        coefs = coefs_from_row(row, available_columns={column})
        self.assertEqual(coefs[2026], Decimal("0.912"))
        self.assertIsNone(coefs[2025])

    def test_coefs_to_route_kwargs(self) -> None:
        kwargs = coefs_to_route_kwargs({2025: Decimal("1.010")})
        self.assertEqual(
            kwargs[route_field_for_year(2025)],
            Decimal("1.010"),
        )
