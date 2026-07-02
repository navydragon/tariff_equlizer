"""Классификация грузов по позициям ЕТСНГ (Приказ ФАС № 862/24)."""
from __future__ import annotations

from core.domain.cargo.formatting import (
    CARGO_CODE_3_WIDTH,
    cargo_code_3_from_etsng,
)

# Импортные перевозки потребительских товаров (позиции ЕТСНГ).
CONSUMER_GOODS_POSITION_SPEC: tuple[str, ...] = (
    "041-044",
    "051-054",
    "075-076",
    "101",
    "121-127",
    "132",
    "133",
    "256",
    "265",
    "266",
    "268",
    "381",
    "402-405",
    "413",
    "417",
    "418",
    "441-443",
    "501-504",
    "511-517",
    "551-556",
    "561-563",
    "571-574",
    "581-584",
    "591-595",
    "601",
    "602",
    "622-626",
    "631-635",
    "641",
    "651-654",
    "661",
    "671",
    "681-685",
    "691",
)

# Внутригосударственные перевозки продовольственных товаров (позиции ЕТСНГ).
FOOD_GOODS_POSITION_SPEC: tuple[str, ...] = (
    "041-044",
    "051-054",
    "501-504",
    "511-517",
    "521",
    "531",
    "551-556",
    "561-563",
    "571-574",
    "581-584",
    "591-592",
    "595",
    "601",
    "602",
)


def expand_etsng_position_spec(spec: list[str] | tuple[str, ...]) -> frozenset[str]:
    """Разворачивает спецификацию позиций ЕТСНГ в множество 3-значных кодов."""
    positions: set[str] = set()
    for item in spec:
        token = item.strip()
        if not token:
            continue
        if "-" in token:
            start_raw, end_raw = token.split("-", 1)
            start = int(start_raw)
            end = int(end_raw)
            if start > end:
                start, end = end, start
            for value in range(start, end + 1):
                positions.add(str(value).zfill(CARGO_CODE_3_WIDTH))
        else:
            positions.add(str(int(token)).zfill(CARGO_CODE_3_WIDTH))
    return frozenset(positions)


CONSUMER_GOODS_POSITIONS = expand_etsng_position_spec(CONSUMER_GOODS_POSITION_SPEC)
FOOD_GOODS_POSITIONS = expand_etsng_position_spec(FOOD_GOODS_POSITION_SPEC)


def classify_cargo_flags(normalized_code: str) -> tuple[bool, bool]:
    """(is_consumer_goods, is_food_goods) для нормализованного кода груза."""
    position = cargo_code_3_from_etsng(normalized_code)
    if not position:
        return False, False
    return (
        position in CONSUMER_GOODS_POSITIONS,
        position in FOOD_GOODS_POSITIONS,
    )
