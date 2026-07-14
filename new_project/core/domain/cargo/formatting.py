from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any

ETSNG_CODE_WIDTH = 6
APP_CARGO_CODE_WIDTH = 5
CARGO_CODE_3_WIDTH = 3


def parse_etsng_code(value: Any) -> str | None:
    """Нормализует код груза из выгрузки РЖД/CSV: trim, только цифры, без int()."""
    if value is None:
        return None
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return str(value) if value >= 0 else None
    if isinstance(value, float):
        if math.isnan(value) or value < 0 or not value.is_integer():
            return None
        return str(int(value))

    # numpy / pandas скаляры
    item = getattr(value, "item", None)
    if callable(item):
        try:
            return parse_etsng_code(item())
        except (ValueError, TypeError, OverflowError):
            return None

    raw = str(value).strip()
    if not raw or raw == "—" or raw.lower() == "nan":
        return None
    # Arrow/pandas float → «161.0»
    if raw.endswith(".0") and raw[:-2].isdigit():
        raw = raw[:-2]
    if not raw.isdigit():
        return None
    return raw


def format_etsng_code(code: int | str | None) -> str:
    """Форматирует код груза ЕТСНГ с ведущими нулями (6 цифр, legacy/импорт)."""
    parsed = parse_etsng_code(code)
    if parsed is None:
        return "" if code is None else str(code).strip()
    return parsed.zfill(ETSNG_CODE_WIDTH)


def format_app_cargo_code(code: int | str | None) -> str:
    """Форматирует код груза для отображения в UI (5-значный формат приложения)."""
    parsed = parse_etsng_code(code)
    if parsed is None:
        return "" if code is None else str(code).strip()
    normalized, _ = normalize_rzd_cargo_code(parsed)
    if not normalized:
        return ""
    if len(normalized) >= APP_CARGO_CODE_WIDTH:
        return normalized
    return normalized.zfill(APP_CARGO_CODE_WIDTH)


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


def normalize_rzd_cargo_code(value: Any) -> tuple[str, str | None]:
    """Преобразует код груза РЖД (4/6) в 5-значный формат приложения.

    Возвращает (нормализованный_код, предупреждение|None).
    """
    parsed = parse_etsng_code(value)
    if parsed is None:
        return "", None

    length = len(parsed)
    if length == APP_CARGO_CODE_WIDTH:
        return parsed, None
    if length == 4:
        return f"0{parsed}", None
    if length == ETSNG_CODE_WIDTH and parsed[0] == "0":
        return parsed[1:], None
    if length == ETSNG_CODE_WIDTH:
        return parsed, (
            f"6-значный код без ведущего нуля: {parsed}"
        )
    return parsed, f"неожиданная длина кода груза ({length}): {parsed}"


def cargo_code_3_from_normalized(value: Any) -> str:
    """Первые 3 цифры нормализованного 5-значного кода груза."""
    normalized, _ = normalize_rzd_cargo_code(value)
    return normalized[:CARGO_CODE_3_WIDTH] if normalized else ""


@dataclass(frozen=True)
class RouteCargoFields:
    main_code: str
    izpod_code: str
    code_3: str
    izpod_3: str
    warnings: tuple[str, ...]


def normalize_optional_izpod_cargo_code(value: Any) -> tuple[str, str, tuple[str, ...]]:
    """Нормализует код груза из-под; невалидный результат → пустые строки.

    Возвращает (izpod_code, izpod_3, warnings).
    izpod_3 всегда берётся из нормализованного 5-значного кода, не из внешнего поля.
    """
    parsed = parse_etsng_code(value)
    if parsed is None:
        return "", "", ()

    izpod_code, izpod_warn = normalize_rzd_cargo_code(value)
    warnings: list[str] = []
    if izpod_warn:
        warnings.append(izpod_warn)

    if len(izpod_code) != APP_CARGO_CODE_WIDTH:
        if izpod_code and not izpod_warn:
            warnings.append(
                f"невалидный код груза из-под (ожидалась длина {APP_CARGO_CODE_WIDTH}): "
                f"{izpod_code}"
            )
        return "", "", tuple(warnings)

    return izpod_code, cargo_code_3_from_normalized(izpod_code), tuple(warnings)


def resolve_route_cargo_fields(main_raw: Any, izpod_raw: Any) -> RouteCargoFields:
    """Вычисляет коды груза маршрута из сырых значений SQLite."""
    warnings: list[str] = []

    main_code, main_warn = normalize_rzd_cargo_code(main_raw)
    if main_warn:
        warnings.append(main_warn)

    izpod_code, izpod_3, izpod_warnings = normalize_optional_izpod_cargo_code(izpod_raw)
    warnings.extend(izpod_warnings)

    return RouteCargoFields(
        main_code=main_code,
        izpod_code=izpod_code,
        code_3=cargo_code_3_from_normalized(main_code),
        izpod_3=izpod_3,
        warnings=tuple(warnings),
    )


def cargo_code_lookup_keys(value: Any) -> list[str]:
    """Варианты кода для поиска Cargo (5 цифр / 6 цифр / без ведущих нулей)."""
    parsed = parse_etsng_code(value)
    if parsed is None:
        return []

    normalized, _ = normalize_rzd_cargo_code(parsed)
    keys: list[str] = []
    for candidate in (
        normalized,
        parsed,
        format_etsng_code(parsed),
        normalized.lstrip("0") if normalized else "",
        f"0{normalized}" if normalized and len(normalized) == APP_CARGO_CODE_WIDTH else "",
    ):
        if candidate and candidate not in keys:
            keys.append(candidate)
    return keys