from dataclasses import dataclass


@dataclass
class ExchangeRateSetDTO:
    id: int
    name: str
    author_id: int
    author_name: str

    @classmethod
    def from_model(cls, rate_set):
        return cls(
            id=rate_set.id,
            name=rate_set.name,
            author_id=rate_set.author_id,
            author_name=str(rate_set.author),
        )


@dataclass
class ExchangeRateValueDTO:
    id: int
    rate_set_id: int
    year: int
    usd_rub: str

    @classmethod
    def from_model(cls, value):
        return cls(
            id=value.id,
            rate_set_id=value.rate_set_id,
            year=value.year,
            usd_rub=str(value.usd_rub),
        )


@dataclass
class UpdateExchangeRateValueDTO:
    scenario_id: int
    rate_set_id: int
    year: int
    usd_rub: str

    def validate_basic(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.year, int):
            errors.append("Год должен быть целым числом")
        if self.usd_rub is None or str(self.usd_rub).strip() == "":
            errors.append("Значение не может быть пустым")
        return errors

