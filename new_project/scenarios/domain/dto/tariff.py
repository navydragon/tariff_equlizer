from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class TariffRuleConditionDTO:
    id: int
    parameter: str
    operator: str
    values: Any
    position: int

    @classmethod
    def from_model(cls, condition):
        return cls(
            id=condition.id,
            parameter=condition.parameter,
            operator=condition.operator,
            values=condition.values,
            position=condition.position,
        )


@dataclass
class TariffRuleYearValueDTO:
    id: int
    year: int
    coefficient: str

    @classmethod
    def from_model(cls, year_value):
        return cls(
            id=year_value.id,
            year=year_value.year,
            coefficient=str(year_value.coefficient),
        )


@dataclass
class TariffRuleDTO:
    id: int
    scenario_id: int
    name: str
    base_percent: str
    position: int
    conditions: list[TariffRuleConditionDTO]
    year_values: list[TariffRuleYearValueDTO]

    @classmethod
    def from_model(cls, rule):
        return cls(
            id=rule.id,
            scenario_id=rule.scenario_id,
            name=rule.name,
            base_percent=str(rule.base_percent),
            position=rule.position,
            conditions=[TariffRuleConditionDTO.from_model(c) for c in rule.conditions.all()],
            year_values=[TariffRuleYearValueDTO.from_model(v) for v in rule.year_values.all()],
        )


@dataclass
class CreateTariffRuleDTO:
    scenario_id: int
    name: str
    base_percent: Optional[str] = None
    position: Optional[int] = None
    conditions: Optional[list[dict]] = None
    year_values: Optional[dict] = None  # {year: coefficient}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Название решения обязательно")
        if self.position is not None and self.position < 0:
            errors.append("Позиция указана некорректно")
        return errors


@dataclass
class UpdateTariffRuleDTO:
    name: Optional[str] = None
    base_percent: Optional[str] = None
    position: Optional[int] = None
    conditions: Optional[list[dict]] = None
    year_values: Optional[dict] = None  # {year: coefficient}

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.name is not None and not self.name.strip():
            errors.append("Название решения не может быть пустым")
        if self.position is not None and self.position < 0:
            errors.append("Позиция указана некорректно")
        return errors

