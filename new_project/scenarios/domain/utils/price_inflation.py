"""Индексация денежных параметров маршрута по инфляции сценария."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from scenarios.models import Scenario, ScenarioPriceChangeSetting

_MONEY_QUANT = Decimal("0.01")

PRICE_CHANGE_TO_ANALYSIS_KEY: dict[str, str] = {
    ScenarioPriceChangeSetting.Parameter.COST: "cost",
    ScenarioPriceChangeSetting.Parameter.OPERATORS: "oper",
    ScenarioPriceChangeSetting.Parameter.TRANSSHIPMENT: "per",
    ScenarioPriceChangeSetting.Parameter.MARKET_PRICE: "price_rub",
}


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT)


def load_inflation_rates_by_year(scenario: Scenario) -> dict[int, Decimal] | None:
    """
    Возвращает ставки инфляции (%) по годам сценария.

    None — если набор инфляции не привязан к сценарию.
    Годы без явного значения в матрице считаются 0% (ячейка «нет» в UI).
    """
    if not scenario.inflation_set_id:
        return None

    inflation_set = scenario.inflation_set
    if inflation_set is None:
        return None

    years = list(range(int(scenario.start_year), int(scenario.end_year) + 1))
    if not years:
        return None

    values_by_year: dict[int, Decimal] = {}
    for row in inflation_set.values.all():
        values_by_year[int(row.year)] = Decimal(row.rate_percent)

    return {
        year: values_by_year.get(year, Decimal("0"))
        for year in years
    }


def index_money_series(
    years: list[int],
    initial: Decimal,
    rates_by_year: dict[int, Decimal],
) -> dict[int, Decimal]:
    """
    Наращивание от базового года: Y0 = initial, Y > Y0 умножается на (1 + rate_Y / 100).
    """
    if not years:
        return {}

    result: dict[int, Decimal] = {}
    prev = _quantize_money(initial)

    for index, year in enumerate(years):
        if index == 0:
            result[year] = prev
            continue

        rate = rates_by_year.get(year, Decimal("0"))
        try:
            factor = Decimal("1") + rate / Decimal("100")
            current = _quantize_money(prev * factor)
        except (InvalidOperation, ZeroDivisionError):
            current = prev

        result[year] = current
        prev = current

    return result
