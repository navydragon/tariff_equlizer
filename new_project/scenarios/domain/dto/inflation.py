from dataclasses import dataclass


@dataclass
class InflationSetDTO:
    id: int
    name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, inflation_set):
        return cls(
            id=inflation_set.id,
            name=inflation_set.name,
            author_id=inflation_set.author_id,
            author_name=str(inflation_set.author),
        )


@dataclass
class InflationValueDTO:
    id: int
    inflation_set_id: int
    year: int
    rate_percent: str

    @classmethod
    def from_model(cls, value):
        return cls(
            id=value.id,
            inflation_set_id=value.inflation_set_id,
            year=value.year,
            rate_percent=str(value.rate_percent),
        )


@dataclass
class UpdateInflationValueDTO:
    scenario_id: int
    inflation_set_id: int
    year: int
    rate_percent: str

    def validate_basic(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.year, int):
            errors.append("Год должен быть целым числом")
        if self.rate_percent is None or str(self.rate_percent).strip() == "":
            errors.append("Значение не может быть пустым")
        return errors
