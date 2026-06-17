"""
DTO (Data Transfer Objects) для справочника грузов (Cargo).
Отделяют формат внешнего ввода/вывода от внутренних моделей Django.
"""
from dataclasses import dataclass
from typing import List, Optional

from core.domain.cargo.formatting import parse_etsng_code


@dataclass
class CargoDTO:
    """DTO для одного груза."""

    code: str
    name: str
    cargo_group_code: Optional[int]
    cargo_group_name: Optional[str]

    @classmethod
    def from_model(cls, cargo) -> "CargoDTO":
        group = cargo.cargo_group
        return cls(
            code=cargo.code,
            name=cargo.name,
            cargo_group_code=group.code if group else None,
            cargo_group_name=group.name if group else None,
        )


@dataclass
class CreateCargoDTO:
    """DTO для создания груза."""

    code: str
    name: str
    cargo_group_code: Optional[int] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if parse_etsng_code(self.code) is None:
            errors.append("Код груза должен быть числовым кодом ЕТСНГ")
        if not self.name or not self.name.strip():
            errors.append("Наименование груза обязательно")
        return errors


@dataclass
class UpdateCargoDTO:
    """DTO для обновления груза."""

    name: Optional[str] = None
    cargo_group_code: Optional[int] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.name is not None and not self.name.strip():
            errors.append("Наименование груза не может быть пустым")
        return errors


@dataclass
class CargoListResultDTO:
    """Результат постраничного списка грузов."""

    items: List[CargoDTO]
    total: int
    page: int
    page_size: int
    total_pages: int
