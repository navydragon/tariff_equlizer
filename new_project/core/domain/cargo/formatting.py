from __future__ import annotations

from typing import Any

ETSNG_CODE_WIDTH = 6


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