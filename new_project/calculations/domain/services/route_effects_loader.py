from __future__ import annotations

import io
import time

import pandas as pd
import pyarrow.csv as pacsv
from django.db import connection

from calculations.domain.services.route_mart_store import (
    MartMeta,
    MartSidecarView,
    save_route_mart,
    try_load_route_mart,
)
from core.domain.cargo.formatting import format_cargo_code_3
from core.domain.route.turnover_coefficients import (
    TURNOVER_COEF_YEARS,
    route_field_for_year,
)
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

_POSTGRES_COPY_CSV_PARSE_OPTIONS = pacsv.ParseOptions(newlines_in_values=True)


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


def _build_routes_sql(*, route_set_id: int | None = None, parameterized: bool = False) -> str:
    if parameterized:
        route_set_filter = "%s"
    else:
        if route_set_id is None:
            raise ValueError("route_set_id is required when parameterized=False")
        route_set_filter = str(int(route_set_id))

    route_table = _table(Route)
    cargo_table = _table(Cargo)
    cargo_group_table = _table(CargoGroup)
    station_table = _table(Station)
    railroad_table = _table(RailRoad)
    wagon_kind_table = _table(WagonKind)
    shipment_type_table = _table(ShipmentType)
    message_type_table = _table(MessageType)
    shipper_table = _table(Shipper)

    return f"""
        SELECT
            r.id,
            r.freight_charge_rub,
            r.transport_volume_tons,
            r.skip_elasticity,
            r.elasticity_source,
            r.model_route_id,
            r.turnover_change_coef_2025,
            r.turnover_change_coef_2026,
            r.turnover_change_coef_2027,
            r.turnover_change_coef_2028,
            r.turnover_change_coef_2029,
            r.turnover_change_coef_2030,
            r.shipper_id,
            COALESCE(NULLIF(TRIM(s.holding), ''), 'Прочие') AS shipper_holding,
            r.cargo_id,
            r.origin_station_id,
            r.destination_station_id,
            r.wagon_kind_id,
            r.shipment_type_id,
            r.message_type_id,
            r.distance_loaded_km,
            COALESCE(NULLIF(TRIM(r.distance_belt), ''), '') AS distance_belt,
            r.distance_belt_midpoint_km,
            CAST(c.code AS TEXT) AS cargo_code,
            cg.name AS cargo_group,
            CAST(cg.code AS TEXT) AS cargo_group_code,
            c.cargo_group_id AS cargo_group_id,
            mr.cargo_id AS mr_cargo_id,
            mr_c.cargo_group_id AS mr_cargo_group_id,
            mr.message_type_id AS mr_message_type_id,
            mr.market_price_per_ton AS mr_market_price_per_ton,
            mr.production_cost_per_ton AS mr_production_cost_per_ton,
            mr.total_cost_per_ton AS mr_total_cost_per_ton,
            mr.rzd_cost_total_per_ton AS mr_rzd_cost_total_per_ton,
            mr.operators_cost_per_ton AS mr_operators_cost_per_ton,
            mr.transshipment_cost_per_ton AS mr_transshipment_cost_per_ton,
            mr.enterprise_load_coefficient AS mr_enterprise_load_coefficient,
            origin_rr.code AS origin_railroad_code,
            origin_rr.direction AS direction_raw,
            dest_rr.code AS destination_railroad_code,
            wk.name AS wagon_kind,
            COALESCE(NULLIF(TRIM(r.shipment_category), ''), '—') AS shipment_category,
            COALESCE(NULLIF(TRIM(r.park_type), ''), '—') AS park_type,
            COALESCE(NULLIF(TRIM(r.cargo_code_3), ''), '') AS cargo_code_3,
            COALESCE(NULLIF(TRIM(r.cargo_code_izpod_3), ''), '') AS cargo_code_izpod_3,
            COALESCE(NULLIF(TRIM(r.cargo_group_izpod), ''), '') AS cargo_group_izpod,
            COALESCE(NULLIF(TRIM(r.special_container_type), ''), '') AS special_container_type,
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
        LEFT JOIN {route_table} mr ON r.model_route_id = mr.id
        LEFT JOIN {cargo_table} mr_c ON mr.cargo_id = mr_c.code
        WHERE r.route_set_id = {route_set_filter}
          AND r.is_model = false
          AND r.freight_charge_rub IS NOT NULL
          AND r.freight_charge_rub > 0
    """


def _coerce_route_mart_numeric_columns(df: pd.DataFrame) -> None:
    for column in (
        "freight_charge_rub",
        "transport_volume_tons",
        "cargo_group_id",
        "mr_cargo_id",
        "mr_cargo_group_id",
        "mr_message_type_id",
        "mr_market_price_per_ton",
        "mr_production_cost_per_ton",
        "mr_total_cost_per_ton",
        "mr_rzd_cost_total_per_ton",
        "mr_operators_cost_per_ton",
        "mr_transshipment_cost_per_ton",
        "mr_enterprise_load_coefficient",
        "distance_loaded_km",
        "distance_belt_midpoint_km",
        *(
            route_field_for_year(year)
            for year in TURNOVER_COEF_YEARS
        ),
    ):
        if column in df.columns:
            df[column] = pd.to_numeric(df[column], errors="coerce")


def _finalize_routes_dataframe(
    df: pd.DataFrame,
    *,
    timings: dict[str, int | str],
    t_before_normalize: float,
) -> tuple[pd.DataFrame, dict[str, int | str]]:
    _coerce_route_mart_numeric_columns(df)
    normalize_route_dimensions(df)
    timings["normalize_ms"] = int((time.perf_counter() - t_before_normalize) * 1000)
    return df, timings


def _fetch_routes_dataframe_legacy(
    route_set_id: int,
) -> tuple[pd.DataFrame, dict[str, int | str]]:
    routes_sql = _build_routes_sql(parameterized=True)

    timings: dict[str, int | str] = {"routes_load_mode": "legacy"}
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

    return _finalize_routes_dataframe(df, timings=timings, t_before_normalize=t_df)


def _fetch_routes_dataframe_postgres_copy(
    route_set_id: int,
) -> tuple[pd.DataFrame, dict[str, int | str]]:
    routes_sql = _build_routes_sql(route_set_id=route_set_id)
    copy_sql = (
        f"COPY ({routes_sql}) TO STDOUT WITH (FORMAT CSV, HEADER TRUE, NULL '')"
    )

    timings: dict[str, int | str] = {"routes_load_mode": "postgres_copy"}
    t0 = time.perf_counter()

    raw_conn = connection.connection
    buffer = io.BytesIO()
    with raw_conn.cursor() as cursor:
        with cursor.copy(copy_sql) as copy:
            while chunk := copy.read():
                buffer.write(chunk)
    t_copy = time.perf_counter()

    timings["routes_sql_execute_ms"] = 0
    timings["routes_copy_read_ms"] = int((t_copy - t0) * 1000)
    timings["routes_fetch_ms"] = timings["routes_copy_read_ms"]

    if buffer.getbuffer().nbytes == 0:
        timings["routes_arrow_parse_ms"] = 0
        timings["dataframe_build_ms"] = 0
        timings["normalize_ms"] = 0
        return pd.DataFrame(), timings

    buffer.seek(0)
    table = pacsv.read_csv(buffer, parse_options=_POSTGRES_COPY_CSV_PARSE_OPTIONS)
    df = table.to_pandas(
        timestamp_as_object=True,
        strings_to_categorical=False,
    )
    t_pandas = time.perf_counter()

    timings["routes_arrow_parse_ms"] = int((t_pandas - t_copy) * 1000)
    timings["dataframe_build_ms"] = timings["routes_arrow_parse_ms"]

    return _finalize_routes_dataframe(df, timings=timings, t_before_normalize=t_pandas)


def fetch_route_set_stats(route_set_id: int) -> tuple[int, int]:
    """Лёгкий агрегат по индексу route_set без JOIN."""
    sql = f"""
        SELECT
            COUNT(*) AS total,
            SUM(
                CASE
                    WHEN freight_charge_rub IS NOT NULL
                         AND freight_charge_rub > 0
                    THEN 1
                    ELSE 0
                END
            ) AS with_charge,
            SUM(
                CASE
                    WHEN transport_volume_tons IS NULL
                         OR transport_volume_tons <= 0
                    THEN 1
                    ELSE 0
                END
            ) AS without_volume
        FROM {_table(Route)}
        WHERE route_set_id = %s
          AND is_model = false
    """
    stats = _read_sql(sql, [route_set_id])
    total = int(stats["total"].iloc[0])
    with_charge = int(stats["with_charge"].iloc[0] or 0)
    without_volume = int(stats["without_volume"].iloc[0] or 0)
    skipped_charge = total - with_charge
    return skipped_charge, without_volume


def fetch_routes_dataframe(route_set_id: int) -> pd.DataFrame:
    """Загружает маршруты с измерениями одним SQL-запросом."""
    df, _meta, _timings = fetch_routes_dataframe_cached_timed(route_set_id)
    return df


def fetch_routes_dataframe_cached_timed(
    route_set_id: int,
    *,
    columns: list[str] | None = None,
    prewarm_masks: bool = True,
) -> tuple[MartSidecarView | pd.DataFrame, MartMeta | None, dict[str, int | str]]:
    """
    Витрина маршрутов (после JOIN и normalize) из parquet-файла или из БД.
    columns: подмножество колонок parquet для ускорения KPI-расчёта.
    """
    timings: dict[str, int | str] = {}

    df, meta, load_timings = try_load_route_mart(
        route_set_id=route_set_id,
        columns=columns,
    )
    timings.update(load_timings)

    if df is not None:
        if meta is None:
            timings["stats_ms"] = 0
            return df, None, timings
        timings["stats_ms"] = 0
        return df, meta, timings

    df, db_timings = fetch_routes_dataframe_timed(route_set_id)
    timings.update(db_timings)

    t_stats = time.perf_counter()
    skipped_charge, without_volume = fetch_route_set_stats(route_set_id)
    timings["stats_ms"] = int((time.perf_counter() - t_stats) * 1000)

    write_timings = save_route_mart(
        route_set_id=route_set_id,
        df=df,
        skipped_charge=skipped_charge,
        routes_without_volume=without_volume,
        prewarm_masks=prewarm_masks,
    )
    timings.update(write_timings)
    timings["cache_hit"] = 0

    if columns is None:
        meta = try_load_route_mart(route_set_id=route_set_id)[1]
        return df, meta, timings

    df, meta, reload_timings = try_load_route_mart(
        route_set_id=route_set_id,
        columns=columns,
    )
    reload_timings.pop("cache_hit", None)
    timings.update(reload_timings)
    return df, meta, timings


def fetch_routes_dataframe_cached(route_set_id: int) -> pd.DataFrame:
    df, _meta, _timings = fetch_routes_dataframe_cached_timed(route_set_id)
    return df


def fetch_routes_dataframe_timed(
    route_set_id: int,
) -> tuple[pd.DataFrame, dict[str, int | str]]:
    """
    Загружает маршруты с измерениями одним SQL-запросом.
    Возвращает DataFrame и под-тайминги (мс) для диагностики.
    """
    if connection.vendor == "postgresql":
        return _fetch_routes_dataframe_postgres_copy(route_set_id)
    return _fetch_routes_dataframe_legacy(route_set_id)


def normalize_route_dimensions(df: pd.DataFrame) -> None:
    df["cargo_group"] = df["cargo_group"].fillna("—").replace("", "—")
    df["cargo_code"] = df["cargo_code"].fillna("—").astype(str)

    direction = df["direction_raw"].fillna("").astype(str).str.strip()
    df["direction"] = direction.mask(direction.eq(""), "—")

    for column in ("wagon_kind", "transport_type", "shipment_category", "park_type"):
        if column in df.columns:
            df[column] = df[column].fillna("—").replace("", "—")

    holding = df["shipper_holding"].fillna("").astype(str).str.strip()
    df["holding"] = holding.mask(holding.eq(""), "Прочие")
    df["shipper_holding"] = df["holding"]

    for column in ("cargo_code_3", "cargo_code_izpod_3"):
        if column in df.columns:
            df[column] = df[column].map(format_cargo_code_3)
