from django.core.management.base import BaseCommand, CommandError

from scenarios.domain.services.base_btd_seed import (
    BASE_SCENARIO_NAME,
    seed_base_btd_for_scenario,
)
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "Загружает базовые тарифные решения (BTD) в базовый сценарий "
        f'"{BASE_SCENARIO_NAME}" (2025–2035, см. матрицу на UI).'
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--scenario-name",
            default=BASE_SCENARIO_NAME,
            help=f'Имя сценария (по умолчанию "{BASE_SCENARIO_NAME}").',
        )

    def handle(self, *args, **options) -> None:
        scenario_name = (options.get("scenario_name") or "").strip()
        if not scenario_name:
            raise CommandError("Параметр --scenario-name не может быть пустым.")

        scenario = Scenario.objects.filter(name=scenario_name).first()
        if scenario is None:
            raise CommandError(
                f'Сценарий "{scenario_name}" не найден. '
                "Сначала выполните: python manage.py create_base_scenario"
            )

        result = seed_base_btd_for_scenario(scenario)
        self.stdout.write(
            self.style.SUCCESS(
                f'BTD для "{scenario_name}" (id={scenario.id}): '
                f"{result.categories_upserted} категорий, "
                f"{result.values_upserted} значений по годам."
            )
        )
