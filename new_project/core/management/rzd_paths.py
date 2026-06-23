"""Пути к базе маршрутов РЖД (SQLite)."""

from pathlib import Path

from django.conf import settings

RZD_DB_FILENAME = "02_2026-06-22.db"
RZD_TABLE = "ИХ_ГП"


def get_rzd_db_path() -> Path:
    return Path(settings.BASE_DIR).parent / "databases" / RZD_DB_FILENAME
