from __future__ import annotations

import getpass
import os

from django.core.management.base import BaseCommand, CommandError

from calculations.domain.services.scenario_compute_warm import (
    warm_scenario_compute,
)


class Command(BaseCommand):
    help = (
        "Прогревает scenario_compute (KPI + compact на диске) для сценариев. "
        "С --force сбрасывает дисковый кеш и warm-статус "
        "и пересобирает сценарий с нуля. "
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
        parser.add_argument(
            "--force",
            action="store_true",
            help=(
                "Сбросить scenario_compute и warm-статус, затем пересобрать KPI и compact. "
                "Используйте при «Ошибка фоновой сборки детализации»."
            ),
        )
        parser.add_argument(
            "--include-rule-breakdown",
            action="store_true",
            help=(
                "Собрать rule_by_year для куба эффектов. "
                "Требует больше памяти и времени."
            ),
        )

    def handle(self, *args, **options) -> None:
        route_set_id = options["route_set_id"]
        scenario_id = options["scenario_id"]
        if route_set_id is None and scenario_id is None:
            raise CommandError("Укажите --route-set-id или --scenario-id.")
        if bool(options["force"]):
            current_user = getpass.getuser()
            service_user = os.environ.get("TARIFF_SERVICE_USER", "tariff")
            if (
                current_user == "root"
                and service_user
                and service_user != current_user
            ):
                raise CommandError(
                    "Не запускайте --force от root: "
                    "дисковые кеши станут недоступны сервису. "
                    f"Запустите команду от пользователя сервиса ({service_user})."
                )

        failed = warm_scenario_compute(
            route_set_id=route_set_id,
            scenario_id=scenario_id,
            compact_timeout_s=float(options["compact_timeout"]),
            force=bool(options["force"]),
            include_rule_breakdown=bool(options["include_rule_breakdown"]),
            write=self.stdout.write,
        )
        if failed:
            raise CommandError(f"Прогрев не завершён для {failed} сценариев.")
