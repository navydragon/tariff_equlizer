from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.management.ipem_economics import import_ipem_coal_2026_model_routes
from core.models import RouteSet


class Command(BaseCommand):
    help = (
        "Импорт model-маршрутов из Уголь_эластика_2026.xlsx в RouteSet "
        "и связка operational-маршрутов РЖД через model_route_id."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--file",
            dest="file_path",
            default="../data/ipem/Уголь_эластика_2026.xlsx",
            help="Путь к XLSX IPEM",
        )
        parser.add_argument(
            "--route-set-code",
            dest="route_set_code",
            default="RZD_2026",
            help="Код RouteSet с маршрутами РЖД",
        )
        parser.add_argument(
            "--dry-run",
            dest="dry_run",
            action="store_true",
            help="Только проверка резолва, без записи в БД",
        )

    def handle(self, *args, **options) -> None:
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

        with transaction.atomic():
            result = import_ipem_coal_2026_model_routes(
                csv_path,
                route_set,
                dry_run=dry_run,
            )
            if dry_run:
                transaction.set_rollback(True)

        for warning in result.duplicate_link_key_warnings:
            self.stderr.write(self.style.WARNING(warning))
        for reason in result.skip_reasons:
            self.stderr.write(self.style.WARNING(reason))

        self.stdout.write(
            self.style.SUCCESS(
                f"Импорт model-маршрутов завершён (dry_run={dry_run}, "
                f"route_set={route_set_code!r})"
            )
        )
        self.stdout.write(f"Строк IPEM: {result.total_rows}")
        self.stdout.write(f"Создано model-маршрутов: {result.created_model_routes}")
        if not dry_run:
            self.stdout.write(
                f"Связано operational-маршрутов: {result.linked_operational_routes}"
            )
        self.stdout.write(f"Пропущено строк: {result.skipped_rows}")
