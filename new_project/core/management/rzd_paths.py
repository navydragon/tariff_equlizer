"""Пути к базе маршрутов РЖД (SQLite)."""

from pathlib import Path

from django.conf import settings

RZD_DB_FILENAME = "01_2026-05-19.db"
RZD_TABLE = "ИХ_ГП"


def get_rzd_db_path() -> Path:
    return Path(settings.BASE_DIR).parent / "data" / RZD_DB_FILENAME
