from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError

from core.management.ipem_economics import (
    build_ipem_match_records,
    require_rapidfuzz,
    write_export_csv,
)
from core.models import RouteSet


class Command(BaseCommand):
    help = (
        "Экспорт строк total_ipem, совпадающих с маршрутами РЖД (станции + груз), "
        "с параметрами экономики в CSV."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            default="total_ipem.csv",
            help="Путь к CSV total_ipem (разделитель ';')",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            default="RZD_2026",
            help="Код RouteSet с маршрутами РЖД",
        )
        parser.add_argument(
            "--output",
            dest="output_path",
            default="scripts/ipem_rzd_economics_2025.csv",
            help="Путь к выходному CSV",
        )
        parser.add_argument(
            "--similarity-threshold",
            dest="similarity_threshold",
            type=int,
            default=90,
            help="Порог fuzzy для груза (0–100)",
        )

    def handle(self, *args, **options) -> None:
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

        output_path = Path(options["output_path"])
        if not output_path.is_absolute():
            output_path = Path(settings.BASE_DIR) / output_path

        route_set_code: str = options["route_set_code"]
        try:
            route_set = RouteSet.objects.get(code=route_set_code)
        except RouteSet.DoesNotExist as exc:
            raise CommandError(f"RouteSet с code={route_set_code!r} не найден") from exc

        build_result = build_ipem_match_records(
            csv_path,
            route_set,
            similarity_threshold=similarity_threshold,
        )
        write_export_csv(output_path, build_result.matched)

        for warning in build_result.duplicate_triple_warnings:
            self.stderr.write(self.style.WARNING(warning))

        self.stdout.write(
            self.style.SUCCESS(
                f"Экспорт завершён: {output_path} "
                f"({len(build_result.matched)} строк с совпадением в РЖД)"
            )
        )
        self.stdout.write(
            f"IPEM всего: {build_result.total_ipem_rows}, "
            f"совпало: {len(build_result.matched)}, "
            f"без груза: {build_result.skipped_no_cargo}, "
            f"без ЕСР: {build_result.skipped_no_esr}, "
            f"нет в РЖД: {build_result.skipped_no_rzd}, "
            f"дубликаты троек: {len(build_result.duplicate_triple_warnings)}"
        )
