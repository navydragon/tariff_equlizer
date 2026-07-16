from io import StringIO

from django.test import SimpleTestCase

from core.management.commands.import_cargos import _parse_cargo_class, _parse_row


class _Style:
    WARNING = staticmethod(lambda msg: msg)


class ImportCargosParseTests(SimpleTestCase):
    def test_parse_row_preserves_rzd_format(self) -> None:
        row = {
            "Код": "016101",
            "Наименование": "АНТРАЦИТ",
            "Код группы груза": "1",
            "Класс": "1",
        }
        parsed = _parse_row(row, stderr=StringIO(), style=_Style())
        self.assertEqual(parsed, ("16101", "АНТРАЦИТ", "1", 1, None))

    def test_parse_row_rejects_non_numeric(self) -> None:
        row = {
            "Код": "ABC",
            "Наименование": "TEST",
            "Код группы груза": "1",
            "Класс": "2",
        }
        self.assertIsNone(_parse_row(row, stderr=StringIO(), style=_Style()))

    def test_parse_row_accepts_empty_class(self) -> None:
        row = {
            "Код": "01100",
            "Наименование": "ПШЕНИЦА",
            "Код группы груза": "9",
            "Класс": "",
        }
        parsed = _parse_row(row, stderr=StringIO(), style=_Style())
        self.assertEqual(parsed, ("01100", "ПШЕНИЦА", "9", None, None))

    def test_parse_cargo_class_values(self) -> None:
        self.assertEqual(_parse_cargo_class("2"), 2)
        self.assertEqual(_parse_cargo_class(3), 3)
        self.assertIsNone(_parse_cargo_class(""))
        self.assertIsNone(_parse_cargo_class("х"))
        self.assertIsNone(_parse_cargo_class("0"))
        self.assertIsNone(_parse_cargo_class(None))
