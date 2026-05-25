"""Начальные значения USD/RUB по данным Банка России для базового сценария."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth import get_user_model

from scenarios.models import ExchangeRateSet, ExchangeRateValue, Scenario

User = get_user_model()

FX_SET_NAME = "Прогноз ЦБ"

# Банк России, макроэкономический опрос (октябрь 2025), медиана прогноза
# аналитиков: курс USD/RUB, руб. за долл., в среднем за год.
# 2029–2035 — вне горизонта опроса, уровень последнего года прогноза (2028).
# https://www.cbr.ru/statistics/ddkp/mo_br/
CBR_USD_RUB_FORECAST: dict[int, str] = {
    2025: "85.6000",
    2026: "94.6000",
    2027: "100.0000",
    2028: "103.7000",
    2029: "103.7000",
    2030: "103.7000",
    2031: "103.7000",
    2032: "103.7000",
    2033: "103.7000",
    2034: "103.7000",
    2035: "103.7000",
}


@dataclass(frozen=True)
class FxSeedResult:
    rate_set_id: int
    values_upserted: int
    attached_to_scenario: bool


def seed_cbr_fx_for_scenario(
    scenario: Scenario,
    *,
    author: User | None = None,
    attach: bool = True,
) -> FxSeedResult:
    """
    Создаёт или обновляет набор курсов «Прогноз ЦБ» и при необходимости привязывает к сценарию.
    """
    owner = author or scenario.author
    if owner is None:
        raise ValueError("author is required to seed exchange rate set")

    rate_set, _ = ExchangeRateSet.objects.get_or_create(
        author=owner,
        name=FX_SET_NAME,
    )

    values_upserted = 0
    for year in range(scenario.start_year, scenario.end_year + 1):
        usd_rub = CBR_USD_RUB_FORECAST.get(year)
        if usd_rub is None:
            continue
        ExchangeRateValue.objects.update_or_create(
            rate_set=rate_set,
            year=year,
            defaults={"usd_rub": Decimal(usd_rub)},
        )
        values_upserted += 1

    attached = False
    if attach and scenario.exchange_rate_set_id != rate_set.id:
        scenario.exchange_rate_set = rate_set
        scenario.save(update_fields=["exchange_rate_set"])
        attached = True

    return FxSeedResult(
        rate_set_id=rate_set.id,
        values_upserted=values_upserted,
        attached_to_scenario=attached,
    )
