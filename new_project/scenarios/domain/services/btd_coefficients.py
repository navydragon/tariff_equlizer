from __future__ import annotations

from decimal import Decimal, InvalidOperation
from typing import Optional, Protocol


class BTDCategoryLike(Protocol):
    id: int


def parse_btd_decimal(value: Optional[str]) -> Optional[Decimal]:
    if value is None:
        return None
    try:
        return Decimal(value)
    except InvalidOperation:
        return None


def compute_total_coefficient_for_year(
    *,
    first_category_id: int,
    other_categories: list[BTDCategoryLike],
    year: int,
    prev_year: int,
    value_map: dict[tuple[int, int], str],
) -> str:
    base_value = parse_btd_decimal(value_map.get((first_category_id, year)))
    if base_value is None:
        return ""

    accumulator = base_value
    for category in other_categories:
        numerator = parse_btd_decimal(value_map.get((category.id, year)))
        denominator = parse_btd_decimal(value_map.get((category.id, prev_year)))
        if numerator is None or denominator in (None, Decimal("0")):
            return ""
        accumulator *= numerator / denominator

    try:
        return str(accumulator.quantize(Decimal("0.0001")))
    except InvalidOperation:
        return ""


def compute_total_coefficient_by_year(
    years: list[int],
    categories: list[BTDCategoryLike],
    value_map: dict[tuple[int, int], str],
) -> dict[str, str]:
    if not years or not categories:
        return {}

    first_year = years[0]
    result: dict[str, str] = {str(first_year): ""}
    if len(years) == 1:
        return result

    first_category = categories[0]
    other_categories = categories[1:]

    for index in range(1, len(years)):
        year = years[index]
        prev_year = years[index - 1]
        result[str(year)] = compute_total_coefficient_for_year(
            first_category_id=first_category.id,
            other_categories=other_categories,
            year=year,
            prev_year=prev_year,
            value_map=value_map,
        )

    return result


def compute_total_coefficient_decimals_by_year(
    years: list[int],
    categories: list[BTDCategoryLike],
    value_map: dict[tuple[int, int], str],
) -> dict[int, Decimal]:
    """
    Итоговый коэффициент BTD по годам. Пустое значение → Decimal('1').
    """
    raw = compute_total_coefficient_by_year(years, categories, value_map)
    result: dict[int, Decimal] = {}
    for year in years:
        parsed = parse_btd_decimal(raw.get(str(year)))
        result[year] = parsed if parsed is not None else Decimal("1")
    return result
