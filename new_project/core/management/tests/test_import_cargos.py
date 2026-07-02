import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.models import Cargo, CargoGroup


class ImportCargosCategoryFlagsTests(TestCase):
    def setUp(self) -> None:
        CargoGroup.objects.create(code=10, name="Остальные грузы", position=10)
        CargoGroup.objects.create(code=11, name="Грузы на своих осях", position=11)

    def test_import_sets_consumer_and_food_flags(self) -> None:
        with tempfile.TemporaryDirectory() as tmp_dir:
            csv_path = Path(tmp_dir) / "cargos.csv"
            with csv_path.open("w", encoding="utf-8-sig", newline="") as handle:
                writer = csv.DictWriter(
                    handle,
                    fieldnames=["Код", "Наименование", "Код группы груза"],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Код": "04101",
                        "Наименование": "АРМАТУРА ГАЗОВ",
                        "Код группы груза": "10",
                    }
                )
                writer.writerow(
                    {
                        "Код": "42201",
                        "Наименование": "ЛОКОМОТИВ СВ ПР",
                        "Код группы груза": "11",
                    }
                )
                writer.writerow(
                    {
                        "Код": "521101",
                        "Наименование": "ПШЕНИЦА",
                        "Код группы груза": "10",
                    }
                )
                writer.writerow(
                    {
                        "Код": "016101",
                        "Наименование": "АНТРАЦИТ",
                        "Код группы груза": "10",
                    }
                )

            call_command("import_cargos", file=str(csv_path), verbosity=0)

        consumer_food = Cargo.objects.get(code="04101")
        self.assertTrue(consumer_food.is_consumer_goods)
        self.assertTrue(consumer_food.is_food_goods)

        locomotive = Cargo.objects.get(code="42201")
        self.assertFalse(locomotive.is_consumer_goods)
        self.assertFalse(locomotive.is_food_goods)

        food_only = Cargo.objects.get(code="521101")
        self.assertFalse(food_only.is_consumer_goods)
        self.assertTrue(food_only.is_food_goods)

        other = Cargo.objects.get(code="16101")
        self.assertFalse(other.is_consumer_goods)
        self.assertFalse(other.is_food_goods)
