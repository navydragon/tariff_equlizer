import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.reference_clear import clear_railroads_catalog
from core.models import RailRoad


class Command(BaseCommand):
    help = "Импортирует перечень железных дорог из core/data/railroads.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить таблицу перед импортом",
        )

    def handle(self, *args, **options):
        csv_path = Path(settings.BASE_DIR) / "core" / "data" / "railroads.csv"

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if options.get("clear"):
            deleted_routes, deleted_stations, deleted_railroads = clear_railroads_catalog()
            self.stdout.write(
                self.style.WARNING(
                    "Справочники очищены перед импортом дорог "
                    f"(маршрутов: {deleted_routes}, станций: {deleted_stations}, "
                    f"дорог: {deleted_railroads})."
                )
            )

        created_count = 0
        updated_count = 0

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {
                "Код дороги",
                "Наименование железной дороги",
                "Страна",
                "Направление",
            }
            if not expected_fields.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"Некорректный заголовок CSV. Ожидались поля: {', '.join(sorted(expected_fields))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                try:
                    code = (row.get("Код дороги") or "").strip()
                    name = (row.get("Наименование железной дороги") or "").strip()
                    country = (row.get("Страна") or "").strip()
                    direction = (row.get("Направление") or "").strip()
                except (KeyError, TypeError) as exc:
                    self.stderr.write(self.style.WARNING(f"Пропуск строки {row!r}: ошибка парсинга ({exc})"))
                    continue

                if not code or not name:
                    self.stderr.write(self.style.WARNING(f"Пропуск строки {row!r}: пустой код или наименование"))
                    continue

                _, created = RailRoad.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "country": country,
                        "direction": direction,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт железных дорог завершён. Создано: {created_count}, обновлено: {updated_count}."
            )
        )

