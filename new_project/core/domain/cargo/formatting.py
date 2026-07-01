from __future__ import annotations

from typing import Any

ETSNG_CODE_WIDTH = 6
CARGO_CODE_3_WIDTH = 3


def parse_etsng_code(value: Any) -> str | None:
    """Нормализует код груза из выгрузки РЖД/CSV: trim, только цифры, без int()."""
    if value is None:
        return None
    raw = str(value).strip()
    if not raw or raw == "—":
        return None
    if not raw.isdigit():
        return None
    return raw


def format_etsng_code(code: int | str | None) -> str:
    """Форматирует код груза ЕТСНГ с ведущими нулями для отображения."""
    parsed = parse_etsng_code(code)
    if parsed is None:
        return "" if code is None else str(code).strip()
    return parsed.zfill(ETSNG_CODE_WIDTH)


def format_cargo_code_3(value: Any) -> str:
    """Трёхзначный код класса груза: SQLite int 16 → «016»."""
    parsed = parse_etsng_code(value)
    if parsed is None:
        return ""
    return parsed.zfill(CARGO_CODE_3_WIDTH)


def cargo_code_3_from_etsng(value: Any) -> str:
    """Первые 3 цифры полного кода ЕТСНГ с сохранением ведущего нуля."""
    formatted = format_etsng_code(value)
    return formatted[:CARGO_CODE_3_WIDTH] if formatted else ""


def cargo_code_lookup_keys(value: Any) -> list[str]:
    """Варианты кода для поиска Cargo (6 цифр / как в CSV / без ведущих нулей)."""
    formatted = format_etsng_code(value)
    if not formatted:
        return []

    keys: list[str] = []
    for candidate in (formatted, parse_etsng_code(value), formatted.lstrip("0")):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys