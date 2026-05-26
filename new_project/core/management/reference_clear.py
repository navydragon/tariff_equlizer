"""Удаление связанных данных перед очисткой справочников (обход on_delete=PROTECT)."""

from __future__ import annotations

from typing import NamedTuple


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


def clear_routes() -> int:
    from core.models import Route

    return _delete_all(Route)


def clear_routes_for_route_set(route_set_id: int) -> int:
    from core.models import Route

    deleted, _ = Route.objects.filter(route_set_id=route_set_id).delete()
    return deleted


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
