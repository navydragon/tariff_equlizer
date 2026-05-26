from __future__ import annotations


def parse_distance_belt_midpoint(belt: str | None) -> int | None:
    """Середина интервала пояса дальности, например «500-1000» → 750."""
    if not belt:
        return None
    text = str(belt).strip()
    if not text or "-" not in text:
        return None
    parts = text.split("-", 1)
    if len(parts) != 2:
        return None
    try:
        start = int(parts[0].strip())
        end = int(parts[1].strip())
    except ValueError:
        return None
    return round((start + end) / 2)


def sync_distance_belt_midpoint(route) -> None:
    """Обновляет distance_belt_midpoint_km на экземпляре Route по distance_belt."""
    route.distance_belt_midpoint_km = parse_distance_belt_midpoint(
        getattr(route, "distance_belt", None),
    )


def backfill_distance_belt_midpoint_db(schema_editor) -> None:
    """Массово заполняет distance_belt_midpoint_km из distance_belt в БД."""
    connection = schema_editor.connection
    vendor = connection.vendor
    if vendor == "postgresql":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE core_route
                SET distance_belt_midpoint_km = (
                    (CAST(split_part(distance_belt, '-', 1) AS INTEGER)
                     + CAST(split_part(distance_belt, '-', 2) AS INTEGER))
                    / 2
                )
                WHERE distance_belt <> ''
                  AND distance_belt LIKE '%-%'
                  AND split_part(distance_belt, '-', 1) ~ '^[0-9]+$'
                  AND split_part(distance_belt, '-', 2) ~ '^[0-9]+$'
                """
            )
        return

    if vendor == "sqlite":
        with connection.cursor() as cursor:
            cursor.execute(
                """
                UPDATE core_route
                SET distance_belt_midpoint_km = (
                    (CAST(substr(distance_belt, 1, instr(distance_belt, '-') - 1) AS INTEGER)
                     + CAST(substr(distance_belt, instr(distance_belt, '-') + 1) AS INTEGER))
                    / 2
                )
                WHERE distance_belt <> ''
                  AND instr(distance_belt, '-') > 0
                """
            )
        return

    from core.models import Route

    batch: list = []
    for route in Route.objects.exclude(distance_belt="").iterator(chunk_size=2000):
        midpoint = parse_distance_belt_midpoint(route.distance_belt)
        if midpoint is None:
            continue
        route.distance_belt_midpoint_km = midpoint
        batch.append(route)
        if len(batch) >= 2000:
            Route.objects.bulk_update(batch, ["distance_belt_midpoint_km"], batch_size=2000)
            batch.clear()
    if batch:
        Route.objects.bulk_update(batch, ["distance_belt_midpoint_km"], batch_size=2000)
