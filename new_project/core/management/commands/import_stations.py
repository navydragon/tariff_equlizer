import csv
from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.models import RailRoad, Region, Station


class Command(BaseCommand):
    help = "Импортирует регионы и станции из core/data/railway_stations.csv"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить таблицу станций (и регионов) перед импортом",
        )

    def handle(self, *args, **options):
        csv_path = Path(settings.BASE_DIR) / "core" / "data" / "railway_stations.csv"

        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        if options.get("clear"):
            deleted_stations, _ = Station.objects.all().delete()
            deleted_regions, _ = Region.objects.all().delete()
            self.stdout.write(
                self.style.WARNING(
                    "Таблицы Station и Region очищены перед импортом "
                    f"(удалено станций: {deleted_stations}, регионов: {deleted_regions})."
                )
            )

        created_regions = 0
        created_stations = 0
        updated_stations = 0
        processed_rows = 0

        # Кешируем созданные/найденные регионы в памяти, чтобы не дергать БД каждый раз
        region_cache: dict[tuple[str, str], Region] = {}
        railroads_by_code: dict[str, RailRoad] = RailRoad.objects.in_bulk()

        with csv_path.open(mode="r", encoding="utf-8-sig", newline="") as f:
            reader = csv.DictReader(f, delimiter=";")

            expected_fields = {
                "Код ЕСР",
                "shortname",
                "fullname",
                "region_shortname",
                "region_fullname",
                "Тип региона",
                "КОД дороги",
            }
            if not expected_fields.issubset(reader.fieldnames or []):
                raise CommandError(
                    "Некорректный заголовок CSV. "
                    f"Ожидались поля: {', '.join(sorted(expected_fields))}, "
                    f"получены: {reader.fieldnames}"
                )

            for row in reader:
                processed_rows += 1
                if processed_rows % 1000 == 0:
                    self.stdout.write(f"Обработано строк: {processed_rows}…")

                try:
                    raw_esr = (row.get("Код ЕСР") or "").strip()
                    shortname = (row.get("shortname") or "").strip()
                    fullname = (row.get("fullname") or "").strip()
                    region_shortname = (row.get("region_shortname") or "").strip()
                    region_fullname = (row.get("region_fullname") or "").strip()
                    region_type = (row.get("Тип региона") or "").strip()
                    railroad_code = (row.get("КОД дороги") or "").strip()
                except (KeyError, TypeError) as exc:
                    self.stderr.write(
                        self.style.WARNING(f"Пропуск строки {row!r}: ошибка парсинга ({exc})")
                    )
                    continue

                if not raw_esr:
                    self.stderr.write(
                        self.style.WARNING(f"Пропуск строки {row!r}: пустой 'Код ЕСР'")
                    )
                    continue

                try:
                    esr_code = int(raw_esr)
                except ValueError:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Пропуск строки {row!r}: 'Код ЕСР' не является числом"
                        )
                    )
                    continue

                if not railroad_code:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Пропуск станции ESR={raw_esr}: пустой 'КОД дороги'"
                        )
                    )
                    continue

                railroad = railroads_by_code.get(railroad_code)
                if railroad is None:
                    self.stderr.write(
                        self.style.WARNING(
                            f"Пропуск станции ESR={raw_esr}: дорога с кодом "
                            f"{railroad_code!r} не найдена"
                        )
                    )
                    continue

                normalized_region_full = region_fullname or region_shortname or "Не указан"
                normalized_region_type = region_type or "Не указан"
                normalized_region_short = region_shortname or region_fullname or "Не указан"

                region_key = (normalized_region_full, normalized_region_type)
                region = region_cache.get(region_key)

                if region is None:
                    region, created = Region.objects.get_or_create(
                        full_name=normalized_region_full,
                        type=normalized_region_type,
                        defaults={
                            "short_name": normalized_region_short,
                        },
                    )
                    region_cache[region_key] = region
                    if created:
                        created_regions += 1

                station_defaults = {
                    "short_name": shortname or fullname,
                    "full_name": fullname or shortname,
                    "region": region,
                    "railroad": railroad,
                }

                _, created_station = Station.objects.update_or_create(
                    esr_code=esr_code,
                    defaults=station_defaults,
                )

                if created_station:
                    created_stations += 1
                else:
                    updated_stations += 1

        self.stdout.write(
            self.style.SUCCESS(
                "Импорт станций завершён. "
                f"Создано регионов: {created_regions}, "
                f"создано станций: {created_stations}, "
                f"обновлено станций: {updated_stations}."
            )
        )

