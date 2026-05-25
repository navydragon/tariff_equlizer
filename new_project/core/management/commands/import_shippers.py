import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.management.refs_paths import get_refs_csv
from core.models import Shipper


class Command(BaseCommand):
    help = "Импортирует грузоотправителей из data/refs-01/shippers.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Путь к CSV (по умолчанию data/refs-01/shippers.csv)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить справочник перед импортом",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"]) if options["file"] else get_refs_csv("shippers.csv")

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if options.get("clear"):
            deleted, _ = Shipper.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(f"Справочник грузоотправителей очищен ({deleted} записей).")
            )

        created_count = 0
        updated_count = 0
        skipped = 0

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            expected = {"ОКПО", "ИНН", "Грузоотправитель", "Холдинг грузоотправителя"}
            if not expected.issubset(reader.fieldnames or []):
                raise CommandError(
                    "Некорректный заголовок CSV. "
                    f"Ожидались поля: {', '.join(sorted(expected))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                name = (row.get("Грузоотправитель") or "").strip()
                if not name:
                    skipped += 1
                    continue

                okpo_raw = (row.get("ОКПО") or "").strip()
                okpo = int(okpo_raw) if okpo_raw else None
                inn = (row.get("ИНН") or "").strip()
                holding = (row.get("Холдинг грузоотправителя") or "").strip()

                _, created = Shipper.objects.update_or_create(
                    okpo=okpo,
                    inn=inn,
                    name=name,
                    defaults={"holding": holding},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт грузоотправителей завершён. "
                f"Создано: {created_count}, обновлено: {updated_count}, "
                f"пропущено: {skipped}."
            )
        )
