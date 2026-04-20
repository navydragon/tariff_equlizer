"""
DTO (Data Transfer Objects) для сценариев.
Отделяют формат внешнего ввода/вывода от внутренних моделей Django.
"""
from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class ScenarioDTO:
    """DTO для передачи данных сценария."""
    id: int
    name: str
    description: str
    start_year: int
    end_year: int
    route_set_id: int
    route_set_name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, scenario):
        """Создает DTO из модели Django."""
        return cls(
            id=scenario.id,
            name=scenario.name,
            description=scenario.description,
            start_year=scenario.start_year,
            end_year=scenario.end_year,
            route_set_id=scenario.route_set_id,
            route_set_name=str(scenario.route_set),
            author_id=scenario.author.id,
            author_name=str(scenario.author),
        )


@dataclass
class CreateScenarioDTO:
    """DTO для создания сценария."""
    name: str
    description: str
    start_year: int
    end_year: int
    base_scenario_id: Optional[int] = None

    def validate(self) -> list[str]:
        """Простая валидация данных."""
        errors = []
        if not self.name or not self.name.strip():
            errors.append("Название сценария обязательно")
        if not self.base_scenario_id:
            errors.append("Необходимо указать базовый сценарий")
        if self.start_year >= self.end_year:
            errors.append("Год начала должен быть меньше года окончания")
        if self.start_year < 2000 or self.end_year > 2100:
            errors.append("Годы должны быть в разумных пределах (2000-2100)")
        return errors


@dataclass
class UpdateScenarioDTO:
    """DTO для обновления сценария."""
    name: Optional[str] = None
    description: Optional[str] = None
    start_year: Optional[int] = None
    end_year: Optional[int] = None
    route_set_id: Optional[int] = None

    def validate(self) -> list[str]:
        """Простая валидация данных."""
        errors = []
        if self.name is not None and not self.name.strip():
            errors.append("Название сценария не может быть пустым")
        if self.start_year is not None and self.end_year is not None:
            if self.start_year >= self.end_year:
                errors.append("Год начала должен быть меньше года окончания")
        if self.start_year is not None and (self.start_year < 2000 or self.start_year > 2100):
            errors.append("Год начала должен быть в пределах 2000-2100")
        if self.end_year is not None and (self.end_year < 2000 or self.end_year > 2100):
            errors.append("Год окончания должен быть в пределах 2000-2100")
        if self.route_set_id is not None and self.route_set_id <= 0:
            errors.append("Набор маршрутов указан некорректно")
        return errors


@dataclass
class ScenarioListDTO:
    """DTO для списка сценариев (упрощенная версия)."""
    id: int
    name: str
    description: str
    start_year: int
    end_year: int
    route_set_id: int
    route_set_name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, scenario):
        """Создает DTO из модели Django."""
        return cls(
            id=scenario.id,
            name=scenario.name,
            description=scenario.description or "",
            start_year=scenario.start_year,
            end_year=scenario.end_year,
            route_set_id=scenario.route_set_id,
            route_set_name=str(scenario.route_set),
            author_id=scenario.author.id,
            author_name=str(scenario.author),
        )


@dataclass
class BTDCategoryDTO:
    """DTO для категории базовых тарифных решений (BTD)."""

    id: int
    name: str
    position: int
    scenario_id: int

    @classmethod
    def from_model(cls, category):
        """Создает DTO из модели Django."""
        return cls(
            id=category.id,
            name=category.name,
            position=category.position,
            scenario_id=category.scenario_id,
        )


@dataclass
class CreateBTDCategoryDTO:
    """DTO для создания категории базовых тарифных решений."""

    name: str
    scenario_id: int
    position: Optional[int] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not self.name or not self.name.strip():
            errors.append("Название категории обязательно")
        if self.position is not None and self.position <= 0:
            errors.append("Позиция должна быть положительным числом")
        return errors


@dataclass
class UpdateBTDCategoryDTO:
    """DTO для обновления категории базовых тарифных решений."""

    name: Optional[str] = None
    position: Optional[int] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.name is not None and not self.name.strip():
            errors.append("Название категории не может быть пустым")
        if self.position is not None and self.position <= 0:
            errors.append("Позиция должна быть положительным числом")
        return errors


@dataclass
class BTDCategoryValueDTO:
    """DTO для значения категории базовых тарифных решений по годам."""

    id: int
    scenario_id: int
    category_id: int
    year: int
    value: str

    @classmethod
    def from_model(cls, category_value):
        """Создает DTO из модели Django."""
        return cls(
            id=category_value.id,
            scenario_id=category_value.scenario_id,
            category_id=category_value.category_id,
            year=category_value.year,
            value=str(category_value.value),
        )


@dataclass
class UpdateBTDCategoryValueDTO:
    """DTO для обновления значения категории (используется x-editable)."""

    scenario_id: int
    category_id: int
    year: int
    value: str

    def validate_basic(self) -> list[str]:
        """Базовая валидация формата (без знания сценария)."""
        errors: list[str] = []
        if not isinstance(self.year, int):
            errors.append("Год должен быть целым числом")
        if self.value is None or str(self.value).strip() == "":
            errors.append("Значение не может быть пустым")
        return errors


# === Tariff Rules (Отдельные тарифные решения) ===


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
