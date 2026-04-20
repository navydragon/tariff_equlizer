import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import Cargo, CargoGroup


def _parse_row(row, stderr, style):
    try:
        raw_code = (row["Код"] or "").strip()
        raw_name = (row["Наименование"] or "").strip()
        raw_group_code = (row["Код группы груза"] or "").strip()
    except (KeyError, TypeError) as exc:
        stderr.write(
            style.WARNING(f"Пропуск строки {row!r}: ошибка парсинга ({exc})")
        )
        return None

    if not raw_code or not raw_name:
        stderr.write(
            style.WARNING(
                f"Пропуск строки {row!r}: пустой код или наименование"
            )
        )
        return None

    try:
        code = int(raw_code)
    except ValueError:
        stderr.write(
            style.WARNING(
                f"Пропуск строки {row!r}: код '{raw_code}' не является целым числом"
            )
        )
        return None

    return code, raw_name, raw_group_code


def _resolve_group(raw_group_code, stderr, style, code):
    if not raw_group_code:
        return None, False

    try:
        group_code_int = int(raw_group_code)
        cargo_group = CargoGroup.objects.get(code=group_code_int)
        return cargo_group, False
    except (ValueError, CargoGroup.DoesNotExist):
        stderr.write(
            style.WARNING(
                f"Пропуск кода {code}: не найдена группа груза "
                f"с кодом '{raw_group_code}'"
            )
        )
        return None, True


class Command(BaseCommand):
    help = "Импортирует номенклатуру грузов ETSNG из core/data/etsng_filled.csv"

    def handle(self, *args, **options):
        csv_path = Path(settings.BASE_DIR) / "core" / "data" / "etsng_filled.csv"

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        created_count = 0
        updated_count = 0
        skipped_no_group = 0

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {"Код", "Наименование", "Код группы груза"}
            if not expected_fields.issubset(reader.fieldnames or []):
                raise CommandError(
                    "Некорректный заголовок CSV. "
                    f"Ожидались поля: {', '.join(sorted(expected_fields))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                parsed = _parse_row(row, self.stderr, self.style)
                if not parsed:
                    continue

                code, raw_name, raw_group_code = parsed
                cargo_group, skipped = _resolve_group(
                    raw_group_code, self.stderr, self.style, code
                )
                if skipped:
                    skipped_no_group += 1
                    continue

                _, created = Cargo.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": raw_name,
                        "cargo_group": cargo_group,
                    },
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт грузов ETSNG завершён. "
                f"Создано: {created_count}, обновлено: {updated_count}, "
                f"пропущено из‑за отсутствующей группы: {skipped_no_group}."
            )
        )

