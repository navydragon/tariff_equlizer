from __future__ import annotations

from dataclasses import dataclass
from typing import List

from core.models import CargoCategoryPosition

VALID_CATEGORIES = frozenset(
    {
        CargoCategoryPosition.Category.CONSUMER_GOODS,
        CargoCategoryPosition.Category.FOOD_GOODS,
    }
)

CATEGORY_LABELS = {
    CargoCategoryPosition.Category.CONSUMER_GOODS: "Потребительские товары",
    CargoCategoryPosition.Category.FOOD_GOODS: "Продовольственные товары",
}


@dataclass
class CargoCategoryPositionDTO:
    category: str
    position: str
    cargos_count: int = 0
    routes_count: int = 0

    def to_dict(self) -> dict:
        return {
            "category": self.category,
            "position": self.position,
            "cargos_count": self.cargos_count,
            "routes_count": self.routes_count,
        }


@dataclass
class CargoCategoryPositionListResultDTO:
    items: List[CargoCategoryPositionDTO]
    category: str
    category_label: str
    total: int


@dataclass
class AddPositionDTO:
    category: str
    position: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.category not in VALID_CATEGORIES:
            errors.append("Неизвестная категория набора")
        normalized = normalize_position(self.position)
        if normalized is None:
            errors.append("Позиция должна быть 3-значным числом ЕТСНГ")
        return errors

    @property
    def normalized_position(self) -> str | None:
        return normalize_position(self.position)


def normalize_position(value: str) -> str | None:
    raw = (value or "").strip()
    if not raw.isdigit():
        return None
    if len(raw) > 3:
        return None
    return raw.zfill(3)
