from django.apps import AppConfig


class CoreConfig(AppConfig):
    name = 'core'

    def ready(self) -> None:
        # Подключаем сигналы (инвалидация кеша витрины маршрутов и пр.)
        from . import signals  # noqa: F401
