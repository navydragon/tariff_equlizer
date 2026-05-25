"""Начальные значения инфляции по прогнозу Банка России для базового сценария."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.contrib.auth import get_user_model

from scenarios.models import InflationSet, InflationValue, Scenario

User = get_user_model()

INFLATION_SET_NAME = "Прогноз ЦБ"

# Банк России, ОНДКП на 2026–2028 (27.10.2025), базовый сценарий:
# годовая инфляция (ИПЦ, декабрь к декабрю предыдущего года), %.
# Для диапазонов — середина интервала; 2029–2035 — целевой уровень 4%.
# https://www.cbr.ru/about_br/publ/ondkp/on_2026_2028/
CBR_INFLATION_FORECAST_PERCENT: dict[int, str] = {
    2025: "6.7500",  # 6,5–7,0
    2026: "4.5000",  # 4,0–5,0
    2027: "4.0000",
    2028: "4.0000",
    2029: "4.0000",
    2030: "4.0000",
    2031: "4.0000",
    2032: "4.0000",
    2033: "4.0000",
    2034: "4.0000",
    2035: "4.0000",
}


@dataclass(frozen=True)
class InflationSeedResult:
    inflation_set_id: int
    values_upserted: int
    attached_to_scenario: bool


def seed_cbr_inflation_for_scenario(
    scenario: Scenario,
    *,
    author: User | None = None,
    attach: bool = True,
) -> InflationSeedResult:
    """
    Создаёт или обновляет набор «Прогноз ЦБ» и при необходимости привязывает к сценарию.
    """
    owner = author or scenario.author
    if owner is None:
        raise ValueError("author is required to seed inflation set")

    inflation_set, _ = InflationSet.objects.get_or_create(
        author=owner,
        name=INFLATION_SET_NAME,
    )

    values_upserted = 0
    for year in range(scenario.start_year, scenario.end_year + 1):
        rate = CBR_INFLATION_FORECAST_PERCENT.get(year)
        if rate is None:
            continue
        InflationValue.objects.update_or_create(
            inflation_set=inflation_set,
            year=year,
            defaults={"rate_percent": Decimal(rate)},
        )
        values_upserted += 1

    attached = False
    if attach and not scenario.inflation_set_id:
        scenario.inflation_set = inflation_set
        scenario.save(update_fields=["inflation_set"])
        attached = True

    return InflationSeedResult(
        inflation_set_id=inflation_set.id,
        values_upserted=values_upserted,
        attached_to_scenario=attached,
    )
