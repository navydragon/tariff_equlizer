"""
Создаёт тестовые тарифные правила BENCH-* (как в benchmark_tariff_rules.py) для ручной проверки UI.

Примеры:
  python manage.py create_bench_tariff_rules
  python manage.py create_bench_tariff_rules --scenario-id 1 --count 10
  python manage.py create_bench_tariff_rules --delete
  python manage.py create_bench_tariff_rules --coverage-only
"""

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from scenarios.domain.services.bench_tariff_rules import (
    BENCH_PREFIX,
    bench_rule_matched_routes,
    build_bench_presets,
    create_bench_rules,
    delete_bench_rules,
    resolve_bench_scenario,
    sample_bench_values,
)

User = get_user_model()


class Command(BaseCommand):
    help = (
        "Создаёт или удаляет тестовые тарифные правила BENCH-* "
        "(набор как в scripts/benchmark_tariff_rules.py)."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--scenario-id",
            type=int,
            default=None,
            help="ID сценария (по умолчанию — «Базовый» или первый в БД).",
        )
        parser.add_argument(
            "--count",
            type=int,
            default=10,
            help="Сколько правил создать (1–10, по умолчанию 10).",
        )
        parser.add_argument(
            "--delete",
            action="store_true",
            help=f"Удалить все правила с префиксом {BENCH_PREFIX!r}.",
        )
        parser.add_argument(
            "--coverage-only",
            action="store_true",
            help="Только показать matched routes для существующих BENCH-* правил.",
        )
        parser.add_argument(
            "--user-id",
            type=int,
            default=None,
            help="ID пользователя для create_rule (по умолчанию — автор сценария).",
        )

    def handle(self, *args, **options) -> None:
        try:
            scenario = resolve_bench_scenario(options["scenario_id"])
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        if options["delete"]:
            removed = delete_bench_rules(scenario_id=scenario.id)
            self.stdout.write(
                self.style.SUCCESS(
                    f"Удалено {removed} правил {BENCH_PREFIX}* в сценарии {scenario.id} "
                    f"({scenario.name!r}).",
                ),
            )
            return

        if options["coverage_only"]:
            self._print_coverage(scenario)
            return

        count = options["count"]
        if count < 1 or count > 10:
            raise CommandError("--count должен быть от 1 до 10")

        user = self._resolve_user(scenario, options["user_id"])
        samples = sample_bench_values()
        presets = build_bench_presets(samples)

        existing = delete_bench_rules(scenario_id=scenario.id)
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f"Удалено {existing} старых правил {BENCH_PREFIX}* перед созданием.",
                ),
            )

        self.stdout.write(
            f"Сценарий {scenario.id} ({scenario.name!r}), route_set_id={scenario.route_set_id}",
        )
        self.stdout.write("Sample values:")
        for key, value in samples.items():
            self.stdout.write(f"  {key}: {value}")

        try:
            rule_ids = create_bench_rules(
                scenario=scenario,
                user=user,
                presets=presets,
                count=count,
            )
        except Exception as exc:
            raise CommandError(str(exc)) from exc

        self.stdout.write(self.style.SUCCESS(f"Создано {len(rule_ids)} правил: {rule_ids}"))
        for index, preset in enumerate(presets[:count], start=1):
            self.stdout.write(
                f"  {index}. {BENCH_PREFIX}{preset.name} "
                f"(coef years: {', '.join(preset.year_values)})",
            )

        self.stdout.write("")
        self.stdout.write(
            "Warm запланирован (debounce 500 ms). Откройте «Эффект от решений» "
            "и проверьте KPI / таблицу без F5 после CRUD.",
        )
        self._print_coverage(scenario)

    def _resolve_user(self, scenario, user_id: int | None):
        if user_id is not None:
            try:
                return User.objects.get(pk=user_id)
            except User.DoesNotExist as exc:
                raise CommandError(f"Пользователь id={user_id} не найден") from exc
        if scenario.author_id:
            return scenario.author
        user = User.objects.filter(is_superuser=True).first() or User.objects.first()
        if user is None:
            raise CommandError("Не найден пользователь для create_rule")
        return user

    def _print_coverage(self, scenario) -> None:
        coverage = bench_rule_matched_routes(scenario)
        if not coverage:
            self.stdout.write(
                self.style.WARNING(
                    "Coverage: нет BENCH-* правил или витрина маршрутов не готова.",
                ),
            )
            return
        self.stdout.write("Matched routes (sidecar masks):")
        for name, matched in coverage:
            self.stdout.write(f"  {name}: {matched:,}")
