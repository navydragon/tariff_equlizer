"""Коэффициенты изменения грузооборота по годам (колонки % L из выгрузки РЖД)."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from typing import Any, Iterable

TURNOVER_COEF_YEARS: tuple[int, ...] = tuple(range(2025, 2031))

_COEF_QUANT = Decimal("0.001")
_COEF_MIN = Decimal("-99.999")
_COEF_MAX = Decimal("99.999")

_ROUTE_FIELD_BY_YEAR: dict[int, str] = {
    year: f"turnover_change_coef_{year}" for year in TURNOVER_COEF_YEARS
}


def sqlite_column_for_year(year: int) -> str:
    return f"{year}_% L год\\год"


def route_field_for_year(year: int) -> str:
    return _ROUTE_FIELD_BY_YEAR[year]


def quantize_coef(value: Any) -> Decimal | None:
    if value is None:
        return None
    raw = str(value).strip().replace(" ", "").replace(",", ".")
    if not raw:
        return None
    try:
        parsed = Decimal(raw)
    except InvalidOperation:
        return None
    if parsed < _COEF_MIN:
        parsed = _COEF_MIN
    elif parsed > _COEF_MAX:
        parsed = _COEF_MAX
    return parsed.quantize(_COEF_QUANT, rounding=ROUND_HALF_UP)


def coef_for_year(
    stored: dict[int, Decimal | None],
    year: int,
) -> Decimal:
    if year not in TURNOVER_COEF_YEARS:
        return Decimal("1")
    value = stored.get(year)
    if value is None:
        return Decimal("1")
    return value


def _row_value(row: Any, column: str) -> Any:
    if hasattr(row, "keys"):
        try:
            keys = row.keys()
        except Exception:
            keys = None
        if keys is not None and column not in keys:
            return None
    try:
        return row[column]
    except (KeyError, IndexError, TypeError):
        return None


def coefs_from_row(
    row: dict[str, Any] | Any,
    *,
    available_columns: Iterable[str] | None = None,
) -> dict[int, Decimal | None]:
    available = set(available_columns) if available_columns is not None else None
    result: dict[int, Decimal | None] = {}
    for year in TURNOVER_COEF_YEARS:
        column = sqlite_column_for_year(year)
        if available is not None and column not in available:
            result[year] = None
            continue
        result[year] = quantize_coef(_row_value(row, column))
    return result


def coefs_to_route_kwargs(coefs: dict[int, Decimal | None]) -> dict[str, Decimal | None]:
    return {
        route_field_for_year(year): coefs.get(year)
        for year in TURNOVER_COEF_YEARS
    }
