from dataclasses import dataclass, field
from typing import Optional


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
    exchange_rate_set_id: int | None
    exchange_rate_set_name: str
    inflation_set_id: int | None
    inflation_set_name: str
    author_id: int
    author_name: str
    price_change_settings: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_model(cls, scenario, *, price_change_settings: dict[str, str] | None = None):
        return cls(
            id=scenario.id,
            name=scenario.name,
            description=scenario.description,
            start_year=scenario.start_year,
            end_year=scenario.end_year,
            route_set_id=scenario.route_set_id,
            route_set_name=str(scenario.route_set),
            exchange_rate_set_id=scenario.exchange_rate_set_id,
            exchange_rate_set_name=(
                str(scenario.exchange_rate_set) if scenario.exchange_rate_set_id else ""
            ),
            inflation_set_id=scenario.inflation_set_id,
            inflation_set_name=(
                str(scenario.inflation_set) if scenario.inflation_set_id else ""
            ),
            author_id=scenario.author.id,
            author_name=str(scenario.author),
            price_change_settings=price_change_settings or {},
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
        errors: list[str] = []
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
    exchange_rate_set_id: Optional[int] = None
    price_change_settings: Optional[dict[str, str]] = None

    def validate(self) -> list[str]:
        errors: list[str] = []
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
        if self.exchange_rate_set_id is not None and self.exchange_rate_set_id <= 0:
            errors.append("Набор курсов валют указан некорректно")
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
    exchange_rate_set_id: int | None
    exchange_rate_set_name: str
    inflation_set_id: int | None
    inflation_set_name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, scenario):
        return cls(
            id=scenario.id,
            name=scenario.name,
            description=scenario.description or "",
            start_year=scenario.start_year,
            end_year=scenario.end_year,
            route_set_id=scenario.route_set_id,
            route_set_name=str(scenario.route_set),
            exchange_rate_set_id=scenario.exchange_rate_set_id,
            exchange_rate_set_name=(
                str(scenario.exchange_rate_set) if scenario.exchange_rate_set_id else ""
            ),
            inflation_set_id=scenario.inflation_set_id,
            inflation_set_name=(
                str(scenario.inflation_set) if scenario.inflation_set_id else ""
            ),
            author_id=scenario.author.id,
            author_name=str(scenario.author),
        )

