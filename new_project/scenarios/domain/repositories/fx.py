from typing import Optional

from scenarios.models import ExchangeRateSet, ExchangeRateValue


class ExchangeRateSetRepository:
    """Репозиторий наборов курсов валют (USD/RUB)."""

    def get_by_id(self, rate_set_id: int) -> Optional[ExchangeRateSet]:
        try:
            return ExchangeRateSet.objects.select_related("author").get(id=rate_set_id)
        except ExchangeRateSet.DoesNotExist:
            return None

    def list_by_author(self, user) -> list[ExchangeRateSet]:
        return list(
            ExchangeRateSet.objects.filter(author=user).order_by(
                "-updated_at", "-created_at", "id"
            )
        )

    def create(self, data: dict) -> ExchangeRateSet:
        rate_set = ExchangeRateSet.objects.create(**data)
        return ExchangeRateSet.objects.select_related("author").get(id=rate_set.id)

    def update(self, rate_set_id: int, data: dict) -> Optional[ExchangeRateSet]:
        try:
            rate_set = ExchangeRateSet.objects.get(id=rate_set_id)
        except ExchangeRateSet.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(rate_set, key, value)
        rate_set.save()
        return ExchangeRateSet.objects.select_related("author").get(id=rate_set.id)

    def delete(self, rate_set_id: int) -> bool:
        deleted, _ = ExchangeRateSet.objects.filter(id=rate_set_id).delete()
        return deleted > 0


class ExchangeRateValueRepository:
    """Репозиторий значений курса USD/RUB по годам для набора."""

    def list_by_set(self, rate_set_id: int):
        return ExchangeRateValue.objects.filter(rate_set_id=rate_set_id)

    def upsert(self, data: dict) -> ExchangeRateValue:
        obj, _created = ExchangeRateValue.objects.update_or_create(
            rate_set=data["rate_set"],
            year=data["year"],
            defaults={"usd_rub": data["usd_rub"]},
        )
        return obj

