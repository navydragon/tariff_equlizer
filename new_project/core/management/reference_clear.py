"""Удаление связанных данных перед очисткой справочников (обход on_delete=PROTECT)."""

from __future__ import annotations

from typing import NamedTuple

from django.db import connection
from django.utils import timezone


class ClearCounts(NamedTuple):
    routes: int = 0
    stations: int = 0
    regions: int = 0
    railroads: int = 0
    cargos: int = 0
    wagon_kinds: int = 0
    shipment_types: int = 0
    message_types: int = 0


def _delete_all(model) -> int:
    deleted, _ = model.objects.all().delete()
    return deleted


def _route_table_sql() -> str:
    from core.models import Route

    return connection.ops.quote_name(Route._meta.db_table)


def _equalizer_preset_table_sql() -> str:
    from core.models import RouteEqualizerPreset

    return connection.ops.quote_name(RouteEqualizerPreset._meta.db_table)


def _delete_equalizer_presets_for_route_set(
    cursor,
    *,
    route_table: str,
    preset_table: str,
    route_set_id: int,
) -> None:
    """Удаляет пресеты эквалайзера для маршрутов указанного набора."""
    cursor.execute(
        f"DELETE FROM {preset_table} "
        f"WHERE route_id IN ("
        f"SELECT id FROM {route_table} WHERE route_set_id = %s"
        f")",
        [route_set_id],
    )


def _fast_clear_routes(*, route_set_id: int | None = None) -> int:
    """Быстрое удаление маршрутов без ORM-сигналов (post_delete на каждую строку).

    Перед TRUNCATE/DELETE очищает ``RouteEqualizerPreset`` (FK на Route),
    иначе PostgreSQL блокирует TRUNCATE.
    """
    from core.models import Route, RouteSet

    table = _route_table_sql()
    preset_table = _equalizer_preset_table_sql()

    if route_set_id is None:
        pending = Route.objects.count()
        if pending == 0:
            return 0
        with connection.cursor() as cursor:
            if connection.vendor == "postgresql":
                cursor.execute(
                    f"TRUNCATE TABLE {preset_table}, {table} RESTART IDENTITY"
                )
            else:
                cursor.execute(f"DELETE FROM {preset_table}")
                cursor.execute(f"DELETE FROM {table}")
        return pending

    pending = Route.objects.filter(route_set_id=route_set_id).count()
    if pending == 0:
        return 0

    has_other_route_sets = Route.objects.exclude(route_set_id=route_set_id).exists()
    with connection.cursor() as cursor:
        if has_other_route_sets or connection.vendor != "postgresql":
            _delete_equalizer_presets_for_route_set(
                cursor,
                route_table=table,
                preset_table=preset_table,
                route_set_id=route_set_id,
            )
            cursor.execute(
                f"DELETE FROM {table} WHERE route_set_id = %s",
                [route_set_id],
            )
            deleted = cursor.rowcount
        else:
            # Единственный набор — TRUNCATE обеих таблиц (FK не мешает).
            cursor.execute(
                f"TRUNCATE TABLE {preset_table}, {table} RESTART IDENTITY"
            )
            deleted = pending

    RouteSet.objects.filter(pk=route_set_id).update(updated_at=timezone.now())
    return deleted


def clear_routes() -> int:
    return _fast_clear_routes()


def clear_routes_for_route_set(route_set_id: int) -> int:
    return _fast_clear_routes(route_set_id=route_set_id)


def clear_stations_and_regions() -> tuple[int, int, int]:
    """Маршруты → станции → регионы."""
    from core.models import Region, Station

    routes = clear_routes()
    stations = _delete_all(Station)
    regions = _delete_all(Region)
    return routes, stations, regions


def clear_stations_only() -> tuple[int, int]:
    """Маршруты → станции (регионы не трогаем)."""
    from core.models import Station

    routes = clear_routes()
    stations = _delete_all(Station)
    return routes, stations


def clear_railroads_catalog() -> tuple[int, int, int]:
    """Маршруты → станции → железные дороги."""
    from core.models import RailRoad, Station

    routes = clear_routes()
    stations = _delete_all(Station)
    railroads = _delete_all(RailRoad)
    return routes, stations, railroads


def clear_cargos_catalog() -> tuple[int, int]:
    """Маршруты → грузы."""
    from core.models import Cargo

    routes = clear_routes()
    cargos = _delete_all(Cargo)
    return routes, cargos


def clear_route_ref_catalog() -> tuple[int, int, int, int]:
    """Маршруты → род вагона, тип отправки, вид сообщения."""
    from core.models import MessageType, ShipmentType, WagonKind

    routes = clear_routes()
    wagon_kinds = _delete_all(WagonKind)
    shipment_types = _delete_all(ShipmentType)
    message_types = _delete_all(MessageType)
    return routes, wagon_kinds, shipment_types, message_types


def clear_all_reference_data() -> ClearCounts:
    """Полная очистка справочников и маршрутов (для prepare_dev --clear-references)."""
    from core.models import (
        Cargo,
        MessageType,
        RailRoad,
        Region,
        ShipmentType,
        Station,
        WagonKind,
    )

    routes = clear_routes()
    stations = _delete_all(Station)
    regions = _delete_all(Region)
    cargos = _delete_all(Cargo)
    railroads = _delete_all(RailRoad)
    wagon_kinds = _delete_all(WagonKind)
    shipment_types = _delete_all(ShipmentType)
    message_types = _delete_all(MessageType)
    return ClearCounts(
        routes=routes,
        stations=stations,
        regions=regions,
        railroads=railroads,
        cargos=cargos,
        wagon_kinds=wagon_kinds,
        shipment_types=shipment_types,
        message_types=message_types,
    )
