from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.ipem_economics import (
    apply_economics_to_rzd_routes,
    build_ipem_match_records,
    load_records_from_export_csv,
    require_rapidfuzz,
)
from core.models import RouteSet


class Command(BaseCommand):
    help = (
        "Проставить из total_ipem (или export CSV) расходы РЖД и блок экономики "
        "во все совпавшие маршруты RouteSet РЖД."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            default="total_ipem.csv",
            help="Путь к total_ipem.csv или к export CSV",
        )
        parser.add_argument(
            "--from-export",
            dest="from_export",
            action="store_true",
            help="Читать уже отфильтрованный export CSV (export_ipem_rzd_economics_2025)",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            default="RZD_2026",
            help="Код RouteSet с маршрутами РЖД",
        )
        parser.add_argument(
            "--similarity-threshold",
            dest="similarity_threshold",
            type=int,
            default=90,
            help="Порог fuzzy для груза при чтении total_ipem (0–100)",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только статистика, без записи в БД",
        )
        parser.add_argument(
            "--batch-size",
            dest="batch_size",
            type=int,
            default=1000,
            help="Размер пакета bulk_update",
        )

    def handle(self, *args, **options) -> None:
        from_export: bool = bool(options["from_export"])
        if not from_export:
            try:
                require_rapidfuzz()
            except RuntimeError as exc:
                raise CommandError(str(exc)) from exc

        similarity_threshold: int = options["similarity_threshold"]
        if not 0 <= similarity_threshold <= 100:
            raise CommandError("similarity-threshold должен быть в диапазоне 0..100")

        csv_path = Path(options["file_path"])
        if not csv_path.is_absolute():
            csv_path = Path(settings.BASE_DIR) / csv_path
        if not csv_path.exists():
            raise CommandError(f"Файл не найден: {csv_path}")

        route_set_code: str = options["route_set_code"]
        try:
            route_set = RouteSet.objects.get(code=route_set_code)
        except RouteSet.DoesNotExist as exc:
            raise CommandError(f"RouteSet с code={route_set_code!r} не найден") from exc

        dry_run: bool = bool(options["dry_run"])
        batch_size: int = options["batch_size"]

        if from_export:
            records = load_records_from_export_csv(csv_path)
            duplicate_warnings: list[str] = []
            skipped_no_cargo = 0
            skipped_no_esr = 0
            skipped_no_rzd = 0
            total_ipem_rows = len(records)
        else:
            build_result = build_ipem_match_records(
                csv_path,
                route_set,
                similarity_threshold=similarity_threshold,
            )
            records = build_result.matched
            duplicate_warnings = build_result.duplicate_triple_warnings
            skipped_no_cargo = build_result.skipped_no_cargo
            skipped_no_esr = build_result.skipped_no_esr
            skipped_no_rzd = build_result.skipped_no_rzd
            total_ipem_rows = build_result.total_ipem_rows

        for warning in duplicate_warnings:
            self.stderr.write(self.style.WARNING(warning))

        with transaction.atomic():
            stats = apply_economics_to_rzd_routes(
                route_set,
                records,
                dry_run=dry_run,
                batch_size=batch_size,
            )
            if dry_run:
                transaction.set_rollback(True)

        self.stdout.write(
            self.style.SUCCESS(
                "Проставление экономики завершено "
                f"(dry_run={dry_run}, route_set={route_set_code!r})"
            )
        )
        self.stdout.write(f"IPEM строк (источник): {total_ipem_rows}")
        if not from_export:
            self.stdout.write(
                f"Совпало для apply: {len(records)}, "
                f"без груза: {skipped_no_cargo}, "
                f"без ЕСР: {skipped_no_esr}, "
                f"нет в РЖД: {skipped_no_rzd}"
            )
        self.stdout.write(
            f"Строк IPEM применено: {stats['ipem_rows_applied']}, "
            f"маршрутов РЖД обновлено: {stats['rzd_routes_updated']}"
        )
