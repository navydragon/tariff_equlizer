from dataclasses import dataclass
from typing import Optional, List


@dataclass
class RailRoadDTO:
    code: str
    name: str
    country: str
    direction: str

    @classmethod
    def from_model(cls, railroad) -> "RailRoadDTO":
        return cls(
            code=railroad.code,
            name=railroad.name,
            country=railroad.country or "",
            direction=railroad.direction or "",
        )


@dataclass
class CreateRailRoadDTO:
    code: str
    name: str
    country: str = ""
    direction: str = ""

    def validate(self) -> list[str]:
        errors: list[str] = []

        code = (self.code or "").strip() if self.code is not None else ""
        name = (self.name or "").strip() if self.name is not None else ""

        if not code:
            errors.append("Код дороги обязателен")
        elif len(code) > 4:
            errors.append("Код дороги не должен превышать 4 символа")

        if not name:
            errors.append("Наименование дороги обязательно")

        return errors


@dataclass
class UpdateRailRoadDTO:
    name: Optional[str] = None
    country: Optional[str] = None
    direction: Optional[str] = None

    def validate(self) -> list[str]:
        errors: list[str] = []

        if self.name is not None and not self.name.strip():
            errors.append("Наименование дороги не может быть пустым")

        if self.country is not None and len(self.country) > 100:
            errors.append("Длина поля 'Страна' не должна превышать 100 символов")

        if self.direction is not None and len(self.direction) > 50:
            errors.append("Длина поля 'Направление' не должна превышать 50 символов")

        return errors


@dataclass
class RailRoadListResultDTO:
    items: List[RailRoadDTO]
    total: int
    page: int
    page_size: int
    total_pages: int

