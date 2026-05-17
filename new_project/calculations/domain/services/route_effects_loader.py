from __future__ import annotations

import pandas as pd
from django.db import connection

def _read_sql(sql: str, params: list | tuple | None = None) -> pd.DataFrame:
    """read_sql через DB-API соединение Django (без предупреждения pandas)."""
    with connection.cursor() as cursor:
        if params:
            cursor.execute(sql, params)
        else:
            cursor.execute(sql)
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
    return pd.DataFrame.from_records(rows, columns=columns)


from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Route,
    ShipmentType,
    Station,
    WagonKind,
)


def _table(model) -> str:
    return model._meta.db_table


def fetch_route_set_stats(route_set_id: int) -> tuple[int, int]:
    """Лёгкий агрегат по индексу route_set без JOIN."""
    sql = f"""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN freight_charge_ths_rub IS NOT NULL
                         AND freight_charge_ths_rub > 0
                    THEN 1
                    ELSE 0
                END
            ) AS with_charge,
            SUM(
                CASE
                    WHEN transport_volume_mln_tons IS NULL
                         OR transport_volume_mln_tons <= 0
                    THEN 1
                    ELSE 0
                END
            ) AS without_volume
        FROM {_table(Route)}
        WHERE route_set_id = %s
    """
    stats = _read_sql(sql, [route_set_id])
    total = int(stats["total"].iloc[0])
    with_charge = int(stats["with_charge"].iloc[0] or 0)
    without_volume = int(stats["without_volume"].iloc[0] or 0)
    skipped_charge = total - with_charge
    return skipped_charge, without_volume


def fetch_routes_dataframe(route_set_id: int) -> pd.DataFrame:
    route_table = _table(Route)
    cargo_table = _table(Cargo)
    cargo_group_table = _table(CargoGroup)
    station_table = _table(Station)
    railroad_table = _table(RailRoad)
    wagon_kind_table = _table(WagonKind)
    shipment_type_table = _table(ShipmentType)
    message_type_table = _table(MessageType)

    routes_sql = f"""
        SELECT
            id,
            freight_charge_ths_rub,
            transport_volume_mln_tons,
            shipper_holding,
            cargo_id,
            origin_station_id,
            destination_station_id,
            wagon_kind_id,
            shipment_type_id,
            message_type_id,
            distance_loaded_km
        FROM {route_table}
        WHERE route_set_id = %s
          AND freight_charge_ths_rub IS NOT NULL
          AND freight_charge_ths_rub > 0
    """
    routes = _read_sql(routes_sql, [route_set_id])
    if routes.empty:
        return routes

    cargo_ids = routes["cargo_id"].dropna().unique().tolist()
    if cargo_ids:
        placeholders = ", ".join(["%s"] * len(cargo_ids))
        cargo_sql = f"""
            SELECT
                c.code AS cargo_id,
                CAST(c.code AS TEXT) AS cargo_code,
                cg.name AS cargo_group,
                CAST(cg.code AS TEXT) AS cargo_group_code
            FROM {cargo_table} c
            LEFT JOIN {cargo_group_table} cg ON c.cargo_group_id = cg.code
            WHERE c.code IN ({placeholders})
        """
        cargo = _read_sql(cargo_sql, cargo_ids)
    else:
        cargo = pd.DataFrame(
            columns=["cargo_id", "cargo_code", "cargo_group", "cargo_group_code"],
        )

    station_ids = pd.unique(
        routes[["origin_station_id", "destination_station_id"]].to_numpy().ravel(),
    )
    station_ids = [int(value) for value in station_ids if pd.notna(value)]
    if station_ids:
        placeholders = ", ".join(["%s"] * len(station_ids))
        stations_sql = f"""
            SELECT
                s.esr_code AS station_id,
                r.code AS railroad_code,
                r.direction AS direction_raw
            FROM {station_table} s
            LEFT JOIN {railroad_table} r ON s.railroad_id = r.code
            WHERE s.esr_code IN ({placeholders})
        """
        stations = _read_sql(stations_sql, station_ids)
    else:
        stations = pd.DataFrame(
            columns=["station_id", "railroad_code", "direction_raw"],
        )

    wagon_kind_sql = f"""
        SELECT id AS wagon_kind_id, name AS wagon_kind
        FROM {wagon_kind_table}
    """
    wagon_kinds = _read_sql(wagon_kind_sql)

    shipment_type_sql = f"""
        SELECT id AS shipment_type_id, name AS shipment_category
        FROM {shipment_type_table}
    """
    shipment_types = _read_sql(shipment_type_sql)

    message_type_sql = f"""
        SELECT id AS message_type_id, name AS transport_type
        FROM {message_type_table}
    """
    message_types = _read_sql(message_type_sql)

    routes = routes.merge(cargo, on="cargo_id", how="left")

    if not stations.empty:
        origin_stations = stations.rename(
            columns={
                "station_id": "origin_station_id",
                "railroad_code": "origin_railroad_code",
            },
        )[["origin_station_id", "origin_railroad_code", "direction_raw"]]
        destination_stations = stations.rename(
            columns={
                "station_id": "destination_station_id",
                "railroad_code": "destination_railroad_code",
            },
        )[["destination_station_id", "destination_railroad_code"]]
        routes = routes.merge(
            origin_stations,
            on="origin_station_id",
            how="left",
        )
        routes = routes.merge(
            destination_stations,
            on="destination_station_id",
            how="left",
        )
    routes = routes.merge(wagon_kinds, on="wagon_kind_id", how="left")
    routes = routes.merge(shipment_types, on="shipment_type_id", how="left")
    routes = routes.merge(message_types, on="message_type_id", how="left")

    normalize_route_dimensions(routes)
    return routes


def normalize_route_dimensions(df: pd.DataFrame) -> None:
    df["cargo_group"] = df["cargo_group"].fillna("—").replace("", "—")
    df["cargo_code"] = df["cargo_code"].fillna("—").astype(str)

    direction = df["direction_raw"].fillna("").astype(str).str.strip()
    df["direction"] = direction.mask(direction.eq(""), "—")

    for column in ("wagon_kind", "transport_type", "shipment_category"):
        df[column] = df[column].fillna("—").replace("", "—")

    df["park_type"] = "—"

    holding = df["shipper_holding"].fillna("").astype(str).str.strip()
    df["holding"] = holding.mask(holding.eq(""), "Прочие")
    df["shipper_holding"] = df["holding"]
