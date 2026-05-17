"""
DTO (Data Transfer Objects) для сценариев.

Пакет разбит по контекстам:
- scenario: сценарии
- btd: базовые тарифные решения
- tariff: отдельные тарифные решения
- fx: курсы валют
- inflation: инфляция
"""

from .btd import (
    BTDCategoryDTO,
    BTDCategoryValueDTO,
    CreateBTDCategoryDTO,
    UpdateBTDCategoryDTO,
    UpdateBTDCategoryValueDTO,
)
from .fx import (
    ExchangeRateSetDTO,
    ExchangeRateValueDTO,
    UpdateExchangeRateValueDTO,
)
from .inflation import (
    InflationSetDTO,
    InflationValueDTO,
    UpdateInflationValueDTO,
)
from .scenario import (
    CreateScenarioDTO,
    ScenarioDTO,
    ScenarioListDTO,
    UpdateScenarioDTO,
)
from .tariff import (
    CreateTariffRuleDTO,
    TariffRuleConditionDTO,
    TariffRuleDTO,
    TariffRuleYearValueDTO,
    UpdateTariffRuleDTO,
)

__all__ = [
    # Scenario
    "ScenarioDTO",
    "CreateScenarioDTO",
    "UpdateScenarioDTO",
    "ScenarioListDTO",
    # BTD
    "BTDCategoryDTO",
    "CreateBTDCategoryDTO",
    "UpdateBTDCategoryDTO",
    "BTDCategoryValueDTO",
    "UpdateBTDCategoryValueDTO",
    # FX
    "ExchangeRateSetDTO",
    "ExchangeRateValueDTO",
    "UpdateExchangeRateValueDTO",
    # Inflation
    "InflationSetDTO",
    "InflationValueDTO",
    "UpdateInflationValueDTO",
    # Tariff rules
    "TariffRuleConditionDTO",
    "TariffRuleYearValueDTO",
    "TariffRuleDTO",
    "CreateTariffRuleDTO",
    "UpdateTariffRuleDTO",
]
