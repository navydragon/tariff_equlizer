"""Заполнить distance_belt_midpoint_km по distance_belt (если миграция прервалась)."""

from django.core.management.base import BaseCommand
from django.db import connection

from core.domain.distance_belt import backfill_distance_belt_midpoint_db


class _SchemaEditorAdapter:
    def __init__(self, connection):
        self.connection = connection


class Command(BaseCommand):
    help = "Пересчитать середину пояса дальности для всех маршрутов"

    def handle(self, *args, **options):
        backfill_distance_belt_midpoint_db(_SchemaEditorAdapter(connection))
        self.stdout.write(self.style.SUCCESS("Backfill distance_belt_midpoint_km завершён."))
