"""Начальные значения базовых тарифных решений для базового сценария."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from scenarios.models import BTDCategory, BTDCategoryValue, Scenario


BASE_SCENARIO_NAME = "Базовый сценарий"

INDEXATION_VALUES: dict[int, str] = {
    2025: "1.125",
    2026: "1.104",
    2027: "1.088",
    2028: "1.062",
    2029: "1.045",
    2030: "1.046",
    2031: "1.046",
    2032: "1.046",
    2033: "1.046",
    2034: "1.046",
    2035: "1.046",
}

CONSTANT_VALUES: dict[str, str] = {
    "Капитальный ремонт": "1.07",
    "Налоговая надбавка": "1.015",
    "Транспортная безопасность": "1.01",
    "Инвестиционный тариф": "1",
}

BTD_DEFINITIONS: list[tuple[str, int, dict[int, str] | None]] = [
    ("Индексация базовая", 1, INDEXATION_VALUES),
    ("Капитальный ремонт", 2, None),
    ("Налоговая надбавка", 3, None),
    ("Транспортная безопасность", 4, None),
    ("Инвестиционный тариф", 5, None),
]


@dataclass(frozen=True)
class BaseBtdSeedResult:
    categories_upserted: int
    values_upserted: int


def seed_base_btd_for_scenario(scenario: Scenario) -> BaseBtdSeedResult:
    """
    Создаёт/обновляет категории и значения BTD для сценария (матрица на UI).
    Итоговый коэффициент на странице считается на лету, в БД не хранится.
    """
    years = list(range(scenario.start_year, scenario.end_year + 1))
    categories_upserted = 0
    values_upserted = 0

    for name, position, value_map in BTD_DEFINITIONS:
        category, _created = BTDCategory.objects.get_or_create(
            scenario=scenario,
            position=position,
            defaults={"name": name},
        )
        categories_upserted += 1
        if category.name != name:
            category.name = name
            category.save(update_fields=["name"])

        for year in years:
            if value_map is not None:
                raw_value = value_map.get(year)
                if raw_value is None:
                    continue
            else:
                raw_value = CONSTANT_VALUES[name]

            BTDCategoryValue.objects.update_or_create(
                scenario=scenario,
                category=category,
                year=year,
                defaults={"value": Decimal(str(raw_value))},
            )
            values_upserted += 1

    return BaseBtdSeedResult(
        categories_upserted=categories_upserted,
        values_upserted=values_upserted,
    )
