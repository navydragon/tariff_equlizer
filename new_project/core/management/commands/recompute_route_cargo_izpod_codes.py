"""Пересчитать нормализованный код груза из-под и деривированный 3-значный код."""

from django.core.management.base import BaseCommand, CommandError

from calculations.domain.services.route_mart_store import (
    invalidate_route_mart_and_schedule_warm,
)
from core.domain.route.cargo_izpod_recompute import recompute_route_cargo_izpod_codes
from core.models import RouteSet


class Command(BaseCommand):
    help = (
        "Пересчитать cargo_code_izpod и cargo_code_izpod_3 "
        "из нормализованного кода из-под для набора маршрутов"
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--route-set-id",
            type=int,
            required=True,
            help="ID набора маршрутов",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только посчитать изменения, не писать в БД",
        )
        parser.add_argument(
            "--no-warm",
            action="store_true",
            help="Не инвалидировать и не греть витрину после записи",
        )

    def handle(self, *args, **options) -> None:
        route_set_id = options["route_set_id"]
        dry_run = bool(options["dry_run"])
        no_warm = bool(options["no_warm"])

        if not RouteSet.objects.filter(pk=route_set_id).exists():
            raise CommandError(f"Набор маршрутов id={route_set_id} не найден")

        result = recompute_route_cargo_izpod_codes(
            route_set_id=route_set_id,
            dry_run=dry_run,
        )
        mode = "dry-run" if dry_run else "apply"
        self.stdout.write(
            self.style.SUCCESS(
                f"[{mode}] route_set={route_set_id}: "
                f"scanned={result.scanned} updated={result.updated} "
                f"cleared_invalid={result.cleared_invalid}"
            )
        )

        if dry_run or no_warm or result.updated == 0:
            return

        refs_version = invalidate_route_mart_and_schedule_warm(
            route_set_id=route_set_id,
        )
        self.stdout.write(
            f"Витрина route_set={route_set_id} инвалидирована "
            f"(refs_version={refs_version}), запланирован warm."
        )
