import csv
from pathlib import Path

from collections import Counter

from django.core.management.base import BaseCommand, CommandError

from core.domain.cargo.etsng_categories import classify_cargo_flags
from core.domain.cargo.formatting import normalize_rzd_cargo_code, parse_etsng_code
from core.management.reference_clear import clear_cargos_catalog
from core.management.refs_paths import get_refs_csv
from core.models import Cargo, CargoGroup


def _parse_cargo_class(raw_value):
    """Парсит класс груза из CSV: число ≥ 1 → int, иначе None."""
    if raw_value is None:
        return None
    raw = str(raw_value).strip()
    if not raw:
        return None
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return None
    if value < 1:
        return None
    return value


def _parse_row(row, stderr, style):
    try:
        raw_code = (row["Код"] or "").strip()
        raw_name = (row["Наименование"] or "").strip()
        raw_group_code = (row["Код группы груза"] or "").strip()
        raw_cargo_class = row.get("Класс")
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

    code = parse_etsng_code(raw_code)
    if code is None:
        stderr.write(
            style.WARNING(
                f"Пропуск строки {row!r}: код '{raw_code}' не является кодом ЕТСНГ"
            )
        )
        return None

    normalized, warn = normalize_rzd_cargo_code(code)
    if not normalized:
        stderr.write(
            style.WARNING(
                f"Пропуск строки {row!r}: не удалось нормализовать код '{raw_code}'"
            )
        )
        return None
    if warn:
        stderr.write(style.WARNING(f"Код {raw_code}: {warn}"))

    cargo_class = _parse_cargo_class(raw_cargo_class)
    return normalized, raw_name, raw_group_code, cargo_class, warn


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
    help = "Импортирует номенклатуру грузов ETSNG из data/refs-01/cargos.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--file",
            type=str,
            default="",
            help="Путь к CSV (по умолчанию data/refs-01/cargos.csv)",
        )
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить справочник грузов перед импортом",
        )

    def handle(self, *args, **options):
        csv_path = Path(options["file"]) if options["file"] else get_refs_csv("cargos.csv")

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if options.get("clear"):
            deleted_routes, deleted_cargos = clear_cargos_catalog()
            self.stdout.write(
                self.style.WARNING(
                    "Справочник грузов очищен "
                    f"(маршрутов: {deleted_routes}, грузов: {deleted_cargos})."
                )
            )

        created_count = 0
        updated_count = 0
        skipped_no_group = 0
        consumer_goods_count = 0
        food_goods_count = 0
        with_class_count = 0
        warning_counts: Counter[str] = Counter()

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {"Код", "Наименование", "Код группы груза", "Класс"}
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

                code, raw_name, raw_group_code, cargo_class, warn = parsed
                if warn:
                    warning_counts[warn] += 1
                cargo_group, skipped = _resolve_group(
                    raw_group_code, self.stderr, self.style, code
                )
                if skipped:
                    skipped_no_group += 1
                    continue

                is_consumer_goods, is_food_goods = classify_cargo_flags(code)
                if is_consumer_goods:
                    consumer_goods_count += 1
                if is_food_goods:
                    food_goods_count += 1
                if cargo_class is not None:
                    with_class_count += 1

                _, created = Cargo.objects.update_or_create(
                    code=code,
                    defaults={
                        "name": raw_name,
                        "cargo_group": cargo_group,
                        "cargo_class": cargo_class,
                        "is_consumer_goods": is_consumer_goods,
                        "is_food_goods": is_food_goods,
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
                f"пропущено из-за отсутствующей группы: {skipped_no_group}, "
                f"с классом: {with_class_count}, "
                f"потребительские: {consumer_goods_count}, "
                f"продовольственные: {food_goods_count}."
            )
        )
        if warning_counts:
            self.stdout.write(self.style.WARNING("Предупреждения по аномальным кодам:"))
            for warning, count in warning_counts.most_common():
                self.stdout.write(f"  {warning}: {count}")
