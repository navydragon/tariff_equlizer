from decimal import Decimal

from django.test import SimpleTestCase

from core.export.formatting import format_value_for_excel


class ExcelExportFormattingTests(SimpleTestCase):
    def test_decimal_string_uses_comma(self) -> None:
        self.assertEqual(format_value_for_excel("1.234"), "1,234")
        self.assertEqual(format_value_for_excel("10.0"), "10,0")

    def test_integer_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("100"), "100")
        self.assertEqual(format_value_for_excel(42), 42)

    def test_text_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("ИТОГО"), "ИТОГО")
        self.assertEqual(format_value_for_excel("Группа груза"), "Группа груза")

    def test_decimal_type_uses_comma(self) -> None:
        self.assertEqual(format_value_for_excel(Decimal("0.100")), "0,100")

    def test_already_comma_unchanged(self) -> None:
        self.assertEqual(format_value_for_excel("1,234"), "1,234")
