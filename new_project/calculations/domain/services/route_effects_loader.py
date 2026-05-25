from __future__ import annotations

import time
import pandas as pd
from django.db import connection

from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Route,
    ShipmentType,
    Shipper,
    Station,
    WagonKind,
)


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
    """Загружает маршруты с измерениями одним SQL-запросом."""
    df, _timings = fetch_routes_dataframe_timed(route_set_id)
    return df


def fetch_routes_dataframe_timed(
    route_set_id: int,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """
    Загружает маршруты с измерениями одним SQL-запросом.
    Возвращает DataFrame и под-тайминги (мс) для диагностики.
    """
    route_table = _table(Route)
    cargo_table = _table(Cargo)
    cargo_group_table = _table(CargoGroup)
    station_table = _table(Station)
    railroad_table = _table(RailRoad)
    wagon_kind_table = _table(WagonKind)
    shipment_type_table = _table(ShipmentType)
    message_type_table = _table(MessageType)
    shipper_table = _table(Shipper)

    routes_sql = f"""
        SELECT
            r.id,
            r.freight_charge_ths_rub,
            r.transport_volume_mln_tons,
            r.shipper_id,
            COALESCE(NULLIF(TRIM(s.holding), ''), 'Прочие') AS shipper_holding,
            r.cargo_id,
            r.origin_station_id,
            r.destination_station_id,
            r.wagon_kind_id,
            r.shipment_type_id,
            r.message_type_id,
            r.distance_loaded_km,
            CAST(c.code AS TEXT) AS cargo_code,
            cg.name AS cargo_group,
            CAST(cg.code AS TEXT) AS cargo_group_code,
            origin_rr.code AS origin_railroad_code,
            origin_rr.direction AS direction_raw,
            dest_rr.code AS destination_railroad_code,
            wk.name AS wagon_kind,
            st.name AS shipment_category,
            mt.name AS transport_type
        FROM {route_table} r
        LEFT JOIN {shipper_table} s ON r.shipper_id = s.id
        LEFT JOIN {cargo_table} c ON r.cargo_id = c.code
        LEFT JOIN {cargo_group_table} cg ON c.cargo_group_id = cg.code
        LEFT JOIN {station_table} origin_st ON r.origin_station_id = origin_st.esr_code
        LEFT JOIN {railroad_table} origin_rr ON origin_st.railroad_id = origin_rr.code
        LEFT JOIN {station_table} dest_st ON r.destination_station_id = dest_st.esr_code
        LEFT JOIN {railroad_table} dest_rr ON dest_st.railroad_id = dest_rr.code
        LEFT JOIN {wagon_kind_table} wk ON r.wagon_kind_id = wk.id
        LEFT JOIN {shipment_type_table} st ON r.shipment_type_id = st.id
        LEFT JOIN {message_type_table} mt ON r.message_type_id = mt.id
        WHERE r.route_set_id = %s
          AND r.freight_charge_ths_rub IS NOT NULL
          AND r.freight_charge_ths_rub > 0
    """

    timings: dict[str, int] = {}
    t0 = time.perf_counter()

    with connection.cursor() as cursor:
        cursor.execute(routes_sql, [route_set_id])
        t_execute = time.perf_counter()
        columns = [col[0] for col in cursor.description]
        rows = cursor.fetchall()
        t_fetch = time.perf_counter()

    timings["routes_sql_execute_ms"] = int((t_execute - t0) * 1000)
    timings["routes_fetch_ms"] = int((t_fetch - t_execute) * 1000)

    if not rows:
        timings["dataframe_build_ms"] = 0
        timings["normalize_ms"] = 0
        return pd.DataFrame(columns=columns), timings

    df = pd.DataFrame.from_records(rows, columns=columns)
    t_df = time.perf_counter()
    timings["dataframe_build_ms"] = int((t_df - t_fetch) * 1000)

    normalize_route_dimensions(df)
    t_norm = time.perf_counter()
    timings["normalize_ms"] = int((t_norm - t_df) * 1000)

    return df, timings


def normalize_route_dimensions(df: pd.DataFrame) -> None:
    df["cargo_group"] = df["cargo_group"].fillna("—").replace("", "—")
    df["cargo_code"] = df["cargo_code"].fillna("—").astype(str)

    direction = df["direction_raw"].fillna("").astype(str).str.strip()
    df["direction"] = direction.mask(direction.eq(""), "—")

    for column in ("wagon_kind", "transport_type", "shipment_category"):
        if column in df.columns:
            df[column] = df[column].fillna("—").replace("", "—")

    df["park_type"] = "—"

    holding = df["shipper_holding"].fillna("").astype(str).str.strip()
    df["holding"] = holding.mask(holding.eq(""), "Прочие")
    df["shipper_holding"] = df["holding"]
