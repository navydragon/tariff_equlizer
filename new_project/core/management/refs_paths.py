"""Пути к CSV-справочникам из data/refs-01."""

from pathlib import Path

from django.conf import settings

REFS_DIR_NAME = "refs-01"


def get_refs_dir() -> Path:
    return Path(settings.BASE_DIR).parent / "data" / REFS_DIR_NAME


def get_refs_csv(filename: str) -> Path:
    return get_refs_dir() / filename
