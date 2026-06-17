from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from calculations.domain.services.scenario_compute_warm import warm_scenario_compute


class Command(BaseCommand):
    help = (
        "Прогревает scenario_compute (KPI + compact на диске) для сценариев. "
        "Запускайте после refresh_deploy_caches --warm-only, пока сервис остановлен."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--route-set-id",
            type=int,
            default=None,
            help="Прогреть все сценарии набора маршрутов.",
        )
        parser.add_argument(
            "--scenario-id",
            type=int,
            default=None,
            help="Прогреть один сценарий.",
        )
        parser.add_argument(
            "--compact-timeout",
            type=int,
            default=180,
            help="Секунд ждать compact на диске (по умолчанию 180).",
        )

    def handle(self, *args, **options) -> None:
        route_set_id = options["route_set_id"]
        scenario_id = options["scenario_id"]
        if route_set_id is None and scenario_id is None:
            raise CommandError("Укажите --route-set-id или --scenario-id.")

        failed = warm_scenario_compute(
            route_set_id=route_set_id,
            scenario_id=scenario_id,
            compact_timeout_s=float(options["compact_timeout"]),
            write=self.stdout.write,
        )
        if failed:
            raise CommandError(f"Прогрев не завершён для {failed} сценариев.")
