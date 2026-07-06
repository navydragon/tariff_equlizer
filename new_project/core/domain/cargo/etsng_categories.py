"""Классификация грузов по позициям ЕТСНГ (Приказ ФАС № 862/24)."""
from __future__ import annotations

from django.core.cache import cache

from core.domain.cargo.formatting import (
    CARGO_CODE_3_WIDTH,
    cargo_code_3_from_normalized,
)

# Импортные перевозки потребительских товаров (позиции ЕТСНГ).
# Используется только для data-migration.
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
# Используется только для data-migration.
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

CACHE_KEY_CONSUMER = "cargo_category_positions:consumer_goods"
CACHE_KEY_FOOD = "cargo_category_positions:food_goods"
CACHE_TTL_SECONDS = 300


def expand_etsng_position_spec(
    spec: list[str] | tuple[str, ...],
) -> frozenset[str]:
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


def clear_cargo_category_positions_cache() -> None:
    cache.delete_many([CACHE_KEY_CONSUMER, CACHE_KEY_FOOD])


def _load_positions_from_db(category: str) -> frozenset[str]:
    from core.models import CargoCategoryPosition

    return frozenset(
        CargoCategoryPosition.objects.filter(category=category).values_list(
            "position",
            flat=True,
        )
    )


def get_consumer_goods_positions() -> frozenset[str]:
    cached = cache.get(CACHE_KEY_CONSUMER)
    if cached is not None:
        return frozenset(cached)

    from core.models import CargoCategoryPosition

    positions = _load_positions_from_db(
        CargoCategoryPosition.Category.CONSUMER_GOODS,
    )
    cache.set(CACHE_KEY_CONSUMER, list(positions), CACHE_TTL_SECONDS)
    return positions


def get_food_goods_positions() -> frozenset[str]:
    cached = cache.get(CACHE_KEY_FOOD)
    if cached is not None:
        return frozenset(cached)

    from core.models import CargoCategoryPosition

    positions = _load_positions_from_db(
        CargoCategoryPosition.Category.FOOD_GOODS,
    )
    cache.set(CACHE_KEY_FOOD, list(positions), CACHE_TTL_SECONDS)
    return positions


def classify_cargo_flags(normalized_code: str) -> tuple[bool, bool]:
    """(is_consumer_goods, is_food_goods) для 5-значного кода груза."""
    position = cargo_code_3_from_normalized(normalized_code)
    if not position:
        return False, False
    return (
        position in get_consumer_goods_positions(),
        position in get_food_goods_positions(),
    )
