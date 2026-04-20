import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import CargoGroup


class Command(BaseCommand):
    help = "Импортирует группы грузов из core/data/cargo_groups.csv"

    def handle(self, *args, **options):
        csv_path = Path(settings.BASE_DIR) / "core" / "data" / "cargo_groups.csv"

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        created_count = 0
        updated_count = 0

        with csv_path.open(mode="r", encoding="utf-8", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {"name", "position", "code"}
            if not expected_fields.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"Некорректный заголовок CSV. Ожидались поля: {', '.join(sorted(expected_fields))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                try:
                    code = int(row["code"])
                    position = int(row["position"])
                    name = (row["name"] or "").strip()
                except (KeyError, TypeError, ValueError) as exc:
                    self.stderr.write(self.style.WARNING(f"Пропуск строки {row!r}: ошибка парсинга ({exc})"))
                    continue

                _, created = CargoGroup.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": name,
                        "position": position,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт групп грузов завершён. Создано: {created_count}, обновлено: {updated_count}."
            )
        )

