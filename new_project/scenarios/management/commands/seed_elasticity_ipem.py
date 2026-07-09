from pathlib import Path

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from scenarios.domain.services.ipem_elasticity_seed import (
    TECH_SHEET_NAME,
    seed_ipem_elasticity_for_scenario,
)
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "Загружает правила эластичности IPEM из листа "
        f"«{TECH_SHEET_NAME}» (по умолчанию из Металлургия_эластика.xlsx) "
        "в набор «2026» и при необходимости привязывает к сценарию."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--scenario-id",
            dest="scenario_id",
            type=int,
            required=True,
            help="ID сценария: при отсутствии elasticity_set привяжет набор к сценарию",
        )
        parser.add_argument(
            "--file",
            dest="file_path",
            default="../data/ipem/Металлургия_эластика.xlsx",
            help="Путь к XLSX IPEM, содержащему лист «Технический лист»",
        )

    def handle(self, *args, **options) -> None:
        scenario_id = int(options["scenario_id"])
        xlsx_path = Path(options["file_path"])
        if not xlsx_path.is_absolute():
            xlsx_path = Path(settings.BASE_DIR) / xlsx_path
        if not xlsx_path.exists():
            raise CommandError(f"Файл не найден: {xlsx_path}")

        try:
            scenario = Scenario.objects.select_related("author").get(id=scenario_id)
        except Scenario.DoesNotExist as exc:
            raise CommandError(f"Сценарий id={scenario_id} не найден") from exc

        with transaction.atomic():
            result = seed_ipem_elasticity_for_scenario(
                scenario,
                author=scenario.author,
                attach=True,
                xlsx_path=xlsx_path,
            )

        self.stdout.write(
            self.style.SUCCESS(
                f"Набор «2026» (id={result.elasticity_set_id}): "
                f"правил={result.rules_upserted}, точек={result.points_upserted}"
                f"{', привязан к сценарию' if result.attached_to_scenario else ''}."
            )
        )

