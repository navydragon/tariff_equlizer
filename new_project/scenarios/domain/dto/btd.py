from dataclasses import dataclass
from typing import Optional


@dataclass
class BTDCategoryDTO:
    """DTO для категории базовых тарифных решений (BTD)."""

    id: int
    name: str
    position: int
    scenario_id: int

    @classmethod
    def from_model(cls, category):
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
        errors: list[str] = []
        if not isinstance(self.year, int):
            errors.append("Год должен быть целым числом")
        if self.value is None or str(self.value).strip() == "":
            errors.append("Значение не может быть пустым")
        return errors

