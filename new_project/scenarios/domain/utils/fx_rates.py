"""Загрузка курсов USD/RUB сценария по годам."""

from __future__ import annotations

from decimal import Decimal

from scenarios.models import Scenario


def load_fx_rates_by_year(scenario: Scenario) -> dict[int, Decimal] | None:
    """
    Возвращает курс USD/RUB (руб. за долл.) по годам сценария.

    None — если набор курсов не привязан к сценарию.
    Годы без явного значения отсутствуют в словаре.
    """
    if not scenario.exchange_rate_set_id:
        return None

    rate_set = scenario.exchange_rate_set
    if rate_set is None:
        return None

    years = list(range(int(scenario.start_year), int(scenario.end_year) + 1))
    if not years:
        return None

    values_by_year: dict[int, Decimal] = {}
    for row in rate_set.values.all():
        values_by_year[int(row.year)] = Decimal(row.usd_rub)

    return values_by_year


def missing_fx_years(
    years: list[int],
    rates_by_year: dict[int, Decimal] | None,
) -> list[int]:
    """Годы сценария, для которых нет положительного курса."""
    if rates_by_year is None:
        return list(years)
    missing: list[int] = []
    for year in years:
        rate = rates_by_year.get(year)
        if rate is None or rate <= 0:
            missing.append(year)
    return missing
