"""
Management команда для создания базового сценария "Базовый сценарий" 2025-2035.
"""
import os

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

        from scenarios.domain.services.base_btd_seed import seed_base_btd_for_scenario

        seed_base_btd_for_scenario(scenario)
        self.stdout.write(
            self.style.SUCCESS(
                "Базовые тарифные решения (BTD) обновлены/созданы."
            )
        )

        # ========= Exchange rates (USD/RUB, прогноз ЦБ) =========
        from scenarios.domain.services.base_fx_seed import (
            FX_SET_NAME,
            seed_cbr_fx_for_scenario,
        )

        fx_result = seed_cbr_fx_for_scenario(
            scenario,
            author=user,
            attach=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Набор курсов «{FX_SET_NAME}» обновлён/создан '
                f"(id={fx_result.rate_set_id}, "
                f"значений: {fx_result.values_upserted}"
                f"{', привязан к сценарию' if fx_result.attached_to_scenario else ''})."
            )
        )

        # ========= Inflation (прогноз ЦБ) =========
        from scenarios.domain.services.base_inflation_seed import (
            INFLATION_SET_NAME,
            seed_cbr_inflation_for_scenario,
        )

        inflation_result = seed_cbr_inflation_for_scenario(
            scenario,
            author=user,
            attach=True,
        )
        self.stdout.write(
            self.style.SUCCESS(
                f'Набор инфляции «{INFLATION_SET_NAME}» обновлён/создан '
                f"(id={inflation_result.inflation_set_id}, "
                f"значений: {inflation_result.values_upserted}"
                f"{', привязан к сценарию' if inflation_result.attached_to_scenario else ''})."
            )
        )
