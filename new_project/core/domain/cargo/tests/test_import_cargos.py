from io import StringIO

from django.test import SimpleTestCase

from core.management.commands.import_cargos import _parse_row


class _Style:
    WARNING = staticmethod(lambda msg: msg)


class ImportCargosParseTests(SimpleTestCase):
    def test_parse_row_preserves_rzd_format(self) -> None:
        row = {
            "Код": "016101",
            "Наименование": "АНТРАЦИТ",
            "Код группы груза": "1",
        }
        parsed = _parse_row(row, stderr=StringIO(), style=_Style())
        self.assertEqual(parsed, ("016101", "АНТРАЦИТ", "1"))

    def test_parse_row_rejects_non_numeric(self) -> None:
        row = {
            "Код": "ABC",
            "Наименование": "TEST",
            "Код группы груза": "1",
        }
        self.assertIsNone(_parse_row(row, stderr=StringIO(), style=_Style()))
