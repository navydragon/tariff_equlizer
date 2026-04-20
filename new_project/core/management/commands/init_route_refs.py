from django.core.management.base import BaseCommand

from core.models import WagonKind, ShipmentType, MessageType


class Command(BaseCommand):
    help = "Инициализирует справочники маршрутов: род вагона, тип отправки, тип сообщения"

    def add_arguments(self, parser):
        parser.add_argument(
            "--clear",
            action="store_true",
            help="Очистить таблицы перед инициализацией",
        )

    def handle(self, *args, **options):
        wagon_kinds = [
            "Полувагоны",
            "Платформы",
            "Прочие",
            "Крытые",
        ]
        shipment_types = [
            "маршрутная",
            "группа вагонов",
            "повагонная",
            "контейнерный поезд",
            "сцеп вагонов",
            "контейнерная",
            "группа вагонов с гружеными контейнерами",
            "сборная поваг.",
        ]
        message_types = [
            "Экспорт",
            "Внутр. перевозки",
            "Импорт",
            "Транзит",
        ]

        if options.get("clear"):
            WagonKind.objects.all().delete()
            ShipmentType.objects.all().delete()
            MessageType.objects.all().delete()
            self.stdout.write(self.style.WARNING("Таблицы справочников очищены."))

        created_total = 0
        updated_total = 0

        def upsert_list(model, values: list[str]) -> tuple[int, int]:
            created = 0
            updated = 0
            for idx, name in enumerate(values, start=1):
                obj, was_created = model.objects.update_or_create(
                    name=name,
                    defaults={
                        "position": idx,
                        "is_active": True,
                    },
                )
                # В случае update_or_create Django не вызывает save() повторно для defaults,
                # но update_or_create внутри вызывает save() на объекте — name_search пересчитается.
                if was_created:
                    created += 1
                else:
                    updated += 1
            return created, updated

        c, u = upsert_list(WagonKind, wagon_kinds)
        created_total += c
        updated_total += u

        c, u = upsert_list(ShipmentType, shipment_types)
        created_total += c
        updated_total += u

        c, u = upsert_list(MessageType, message_types)
        created_total += c
        updated_total += u

        self.stdout.write(
            self.style.SUCCESS(
                f"Инициализация справочников завершена. Создано: {created_total}, обновлено: {updated_total}."
            )
        )

