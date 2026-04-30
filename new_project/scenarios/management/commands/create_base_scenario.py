"""
Management команда для создания базового сценария "Базовый сценарий" 2025-2035.
"""
import os
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model

from core.models import RouteSet


User = get_user_model()


class Command(BaseCommand):
    help = 'Создает базовый сценарий "Базовый сценарий" с годами 2025-2035'

    def handle(self, *args, **options):
        # Получаем первого суперпользователя или создаем нового
        user = User.objects.filter(is_superuser=True).first()

        if not user:
            self.stdout.write(
                self.style.WARNING(
                    'Суперпользователь не найден. Создаю нового...'
                )
            )
            # Создаем временного суперпользователя для команды
            bootstrap_password = os.environ.get("BOOTSTRAP_ADMIN_PASSWORD")
            if not bootstrap_password:
                raise RuntimeError(
                    "BOOTSTRAP_ADMIN_PASSWORD is required when "
                    "no superuser exists."
                )
            user = User.objects.create_superuser(
                login='admin',
                password=bootstrap_password,
                first_name='Admin',
                last_name='User',
                email='admin@example.com'
            )
            self.stdout.write(
                self.style.SUCCESS(f'Создан суперпользователь: {user.login}')
            )

        # Проверяем, не существует ли уже базовый сценарий
        from scenarios.models import Scenario
        existing = Scenario.objects.filter(name="Базовый сценарий").first()
        scenario = existing

        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f'Сценарий "Базовый сценарий" уже существует (ID: {existing.id})'
                )
            )
        else:
            # route_set обязательный (NOT NULL), поэтому подставляем тех. набор.
            route_set, _ = RouteSet.objects.get_or_create(
                code="DEFAULT_ROUTE_SET",
                defaults={"name": "Технический набор маршрутов"},
            )

            # Создаем базовый сценарий через репозиторий напрямую
            # (так как это первый базовый сценарий, ему не нужен базовый
            # сценарий для наследования)
            from scenarios.domain.repositories import ScenarioRepository

            repository = ScenarioRepository()
            scenario = repository.create(
                {
                    "name": "Базовый сценарий",
                    "description": (
                        "Базовый сценарий для работы с тарифами на период 2025-2035"
                    ),
                    "start_year": 2025,
                    "end_year": 2035,
                    "route_set": route_set,
                    "author": user,
                }
            )

            self.stdout.write(
                self.style.SUCCESS(
                    f'Успешно создан базовый сценарий "Базовый сценарий" '
                    f"(ID: {scenario.id})"
                )
            )

        # ========= BTDCategory + BTDCategoryValue (базовые тарифные решения) =========
        # Эти данные нужны для матрицы на странице "Базовые тарифные решения".
        from scenarios.models import BTDCategory, BTDCategoryValue

        years = list(range(scenario.start_year, scenario.end_year + 1))

        indexation_values: dict[int, str] = {
            2025: "1.125",
            2026: "1.104",
            2027: "1.088",
            2028: "1.062",
            2029: "1.045",
            2030: "1.046",
            2031: "1.046",
            2032: "1.046",
            2033: "1.046",
            2034: "1.046",
            2035: "1.046",
        }

        constant_values: dict[str, str] = {
            "Капитальный ремонт": "1.07",
            "Налоговая надбавка": "1.015",
            "Транспортная безопасность": "1.01",
            "Инвестиционный тариф": "1",
        }

        btd_definitions: list[tuple[str, int, dict[int, str] | None]] = [
            ("Индексация базовая", 1, indexation_values),
            ("Капитальный ремонт", 2, None),
            ("Налоговая надбавка", 3, None),
            ("Транспортная безопасность", 4, None),
            ("Инвестиционный тариф", 5, None),
        ]

        for name, position, value_map in btd_definitions:
            category, _created = BTDCategory.objects.get_or_create(
                scenario=scenario,
                position=position,
                defaults={"name": name},
            )
            if category.name != name:
                category.name = name
                category.save(update_fields=["name"])

            for year in years:
                if value_map is not None:
                    raw_value = value_map.get(year)
                    if raw_value is None:
                        continue
                else:
                    raw_value = constant_values[name]

                BTDCategoryValue.objects.update_or_create(
                    scenario=scenario,
                    category=category,
                    year=year,
                    defaults={"value": Decimal(str(raw_value))},
                )

        self.stdout.write(
            self.style.SUCCESS(
                "Базовые тарифные решения (BTD) обновлены/созданы."
            )
        )

        # ========= Exchange rates (USD/RUB) =========
        from scenarios.models import ExchangeRateSet, ExchangeRateValue

        if scenario.exchange_rate_set_id:
            rate_set = scenario.exchange_rate_set
        else:
            rate_set, _ = ExchangeRateSet.objects.get_or_create(
                author=user,
                name="Базовый курс USD/RUB",
            )
            scenario.exchange_rate_set = rate_set
            scenario.save(update_fields=["exchange_rate_set"])

        for year in years:
            ExchangeRateValue.objects.update_or_create(
                rate_set=rate_set,
                year=year,
                defaults={"usd_rub": Decimal("1.0000")},
            )

        self.stdout.write(
            self.style.SUCCESS("Набор курсов валют обновлён/создан.")
        )
