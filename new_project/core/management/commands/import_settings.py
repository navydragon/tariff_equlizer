import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Setting


class Command(BaseCommand):
    help = "Импортирует настройки приложения из CSV (code;description;value)"

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Путь к CSV (по умолчанию core/data/settings.csv)",
        )

    def handle(self, *args, **options) -> None:
        file_arg = (options.get("file") or "").strip()
        if file_arg:
            csv_path = Path(file_arg)
            if not csv_path.is_absolute():
                csv_path = Path(settings.BASE_DIR) / csv_path
        else:
            csv_path = Path(settings.BASE_DIR) / "core" / "data" / "settings.csv"

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        created_count = 0
        updated_count = 0

        with csv_path.open(mode="r", encoding="utf-8", newline="") as handle:
            reader = csv.DictReader(handle, delimiter=";")
            expected = {"code", "description", "value"}
            if not expected.issubset(reader.fieldnames or []):
                raise CommandError(
                    f"Некорректный заголовок CSV. Ожидались: {', '.join(sorted(expected))}, "
                    f"получены: {reader.fieldnames}",
                )

            for row in reader:
                code = (row.get("code") or "").strip()
                if not code:
                    self.stderr.write(
                        self.style.WARNING(f"Пропуск строки без code: {row!r}"),
                    )
                    continue

                description = (row.get("description") or "").strip()
                value = (row.get("value") or "").strip()

                _, created = Setting.objects.update_or_create(
                    code=code,
                    defaults={
                        "description": description,
                        "value": value,
                    },
                )
                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт настроек завершён. Создано: {created_count}, обновлено: {updated_count}.",
            ),
        )
