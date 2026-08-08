"""
Переносит коэффициенты отдельных тарифных решений с одного года на другой.

Пример:
  python manage.py shift_tariff_rule_year_coefficients \\
    --scenario-id 1 --from-year 2026 --to-year 2027
"""

from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from scenarios.domain.services.shift_tariff_rule_years import (
    shift_tariff_rule_year_coefficients,
)
from scenarios.models import Scenario


class Command(BaseCommand):
    help = (
        "В отдельных тарифных решениях сценария копирует коэффициенты "
        "из --from-year в --to-year и ставит в --from-year значение 1."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--scenario-id",
            type=int,
            required=True,
            help="ID сценария.",
        )
        parser.add_argument(
            "--from-year",
            type=int,
            required=True,
            help="Год-источник коэффициентов (после переноса станет 1).",
        )
        parser.add_argument(
            "--to-year",
            type=int,
            required=True,
            help="Год-назначение (получит коэффициенты из --from-year).",
        )
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Только посчитать изменения, без записи в БД.",
        )

    def handle(self, *args, **options) -> None:
        scenario_id = options["scenario_id"]
        from_year = options["from_year"]
        to_year = options["to_year"]
        dry_run = bool(options["dry_run"])

        scenario = Scenario.objects.filter(id=scenario_id).first()
        if scenario is None:
            raise CommandError(f"Сценарий id={scenario_id} не найден.")

        if from_year == to_year:
            raise CommandError("Параметры --from-year и --to-year должны отличаться.")

        for year, label in ((from_year, "--from-year"), (to_year, "--to-year")):
            if year < scenario.start_year or year > scenario.end_year:
                raise CommandError(
                    f"{label}={year} вне диапазона сценария "
                    f"{scenario.start_year}–{scenario.end_year}."
                )

        try:
            result = shift_tariff_rule_year_coefficients(
                scenario=scenario,
                from_year=from_year,
                to_year=to_year,
                dry_run=dry_run,
            )
        except ValueError as exc:
            raise CommandError(str(exc)) from exc

        prefix = "[dry-run] " if dry_run else ""
        self.stdout.write(
            self.style.SUCCESS(
                f"{prefix}Сценарий {scenario.id} ({scenario.name!r}): "
                f"правил={result.rules_total}, "
                f"перенесено {from_year}→{to_year}: {result.moved}, "
                f"{from_year}=1: {result.source_reset_to_one}."
            )
        )
