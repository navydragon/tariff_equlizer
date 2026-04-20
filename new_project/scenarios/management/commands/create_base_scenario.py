"""
Management команда для создания базового сценария "Базовый сценарий" 2025-2035.
"""
from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model


User = get_user_model()


class Command(BaseCommand):
    help = 'Создает базовый сценарий "Базовый сценарий" с годами 2025-2035'

    def handle(self, *args, **options):
        # Получаем первого суперпользователя или создаем нового
        user = User.objects.filter(is_superuser=True).first()
        
        if not user:
            self.stdout.write(
                self.style.WARNING('Суперпользователь не найден. Создаю нового...')
            )
            # Создаем временного суперпользователя для команды
            user = User.objects.create_superuser(
                login='admin',
                password='admin',
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
        
        if existing:
            self.stdout.write(
                self.style.WARNING(
                    f'Сценарий "Базовый сценарий" уже существует (ID: {existing.id})'
                )
            )
            return

        # Создаем базовый сценарий через репозиторий напрямую
        # (так как это первый базовый сценарий, ему не нужен базовый сценарий для наследования)
        from scenarios.domain.repositories import ScenarioRepository
        repository = ScenarioRepository()
        
        scenario = repository.create({
            "name": "Базовый сценарий",
            "description": "Базовый сценарий для работы с тарифами на период 2025-2035",
            "start_year": 2025,
            "end_year": 2035,
            "author": user,
        })

        self.stdout.write(
            self.style.SUCCESS(
                f'Успешно создан базовый сценарий "Базовый сценарий" (ID: {scenario.id})'
            )
        )
