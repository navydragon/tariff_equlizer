import csv
import tempfile
from pathlib import Path

from django.core.management import call_command
from django.test import TestCase

from core.domain.cargo.dto import CreateCargoDTO, UpdateCargoDTO
from core.domain.cargo.services import CargoService
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
                    fieldnames=["Код", "Наименование", "Код группы груза", "Класс"],
                    delimiter=";",
                )
                writer.writeheader()
                writer.writerow(
                    {
                        "Код": "04101",
                        "Наименование": "АРМАТУРА ГАЗОВ",
                        "Код группы груза": "10",
                        "Класс": "3",
                    }
                )
                writer.writerow(
                    {
                        "Код": "42201",
                        "Наименование": "ЛОКОМОТИВ СВ ПР",
                        "Код группы груза": "11",
                        "Класс": "",
                    }
                )
                writer.writerow(
                    {
                        "Код": "521101",
                        "Наименование": "ПШЕНИЦА",
                        "Код группы груза": "10",
                        "Класс": "2",
                    }
                )
                writer.writerow(
                    {
                        "Код": "016101",
                        "Наименование": "АНТРАЦИТ",
                        "Код группы груза": "10",
                        "Класс": "1",
                    }
                )

            call_command("import_cargos", file=str(csv_path), verbosity=0)

        consumer_food = Cargo.objects.get(code="04101")
        self.assertTrue(consumer_food.is_consumer_goods)
        self.assertTrue(consumer_food.is_food_goods)
        self.assertEqual(consumer_food.cargo_class, 3)

        locomotive = Cargo.objects.get(code="42201")
        self.assertFalse(locomotive.is_consumer_goods)
        self.assertFalse(locomotive.is_food_goods)
        self.assertIsNone(locomotive.cargo_class)

        food_only = Cargo.objects.get(code="521101")
        self.assertFalse(food_only.is_consumer_goods)
        self.assertTrue(food_only.is_food_goods)
        self.assertEqual(food_only.cargo_class, 2)

        other = Cargo.objects.get(code="16101")
        self.assertFalse(other.is_consumer_goods)
        self.assertFalse(other.is_food_goods)
        self.assertEqual(other.cargo_class, 1)


class CargoClassServiceTests(TestCase):
    def setUp(self) -> None:
        self.group = CargoGroup.objects.create(code=9, name="Хлебные", position=1)
        self.service = CargoService()

    def test_create_cargo_with_class(self) -> None:
        dto = CreateCargoDTO(
            code="01100",
            name="ПШЕНИЦА",
            cargo_group_code=9,
            cargo_class=2,
        )
        cargo, errors = self.service.create_cargo(dto)
        self.assertEqual(errors, [])
        self.assertIsNotNone(cargo)
        self.assertEqual(cargo.cargo_class, 2)
        self.assertEqual(Cargo.objects.get(code="01100").cargo_class, 2)

    def test_create_rejects_invalid_class(self) -> None:
        dto = CreateCargoDTO(
            code="01100",
            name="ПШЕНИЦА",
            cargo_class=0,
        )
        cargo, errors = self.service.create_cargo(dto)
        self.assertIsNone(cargo)
        self.assertTrue(errors)

    def test_update_clears_cargo_class(self) -> None:
        Cargo.objects.create(
            code="01100",
            name="ПШЕНИЦА",
            cargo_group=self.group,
            cargo_class=2,
        )
        dto = UpdateCargoDTO(clear_cargo_class=True)
        cargo, errors = self.service.update_cargo("01100", dto)
        self.assertEqual(errors, [])
        self.assertIsNone(cargo.cargo_class)
