import csv
from pathlib import Path

from django.core.management.base import BaseCommand, CommandError

from core.management.reference_clear import clear_stations_and_regions
from core.management.refs_paths import get_refs_csv
from core.models import Region


class Command(BaseCommand):
    help = "Импортирует регионы из data/refs-01/regions.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Путь к CSV (по умолчанию data/refs-01/regions.csv)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить справочник регионов перед импортом (сначала удаляются станции)",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"]) if options["file"] else get_refs_csv("regions.csv")

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if options.get("clear"):
            deleted_routes, deleted_stations, deleted_regions = clear_stations_and_regions()
            self.stdout.write(
                self.style.WARNING(
                    "Справочники очищены перед импортом регионов "
                    f"(маршрутов: {deleted_routes}, станций: {deleted_stations}, "
                    f"регионов: {deleted_regions})."
                )
            )

        created_count = 0
        updated_count = 0
        skipped = 0

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")
            expected = {"region_shortname", "region_fullname", "Тип региона"}
            if not expected.issubset(reader.fieldnames or []):
                raise CommandError(
                    "Некорректный заголовок CSV. "
                    f"Ожидались поля: {', '.join(sorted(expected))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                short_name = (row.get("region_shortname") or "").strip()
                full_name = (row.get("region_fullname") or "").strip()
                region_type = (row.get("Тип региона") or "").strip()

                if not full_name:
                    skipped += 1
                    continue

                normalized_short = short_name or full_name
                normalized_type = region_type or "Не указан"

                _, created = Region.objects.update_or_create(
                    full_name=full_name,
                    type=normalized_type,
                    defaults={"short_name": normalized_short},
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт регионов завершён. "
                f"Создано: {created_count}, обновлено: {updated_count}, "
                f"пропущено: {skipped}."
            )
        )
