from typing import Optional

from scenarios.models import InflationSet, InflationValue


class InflationSetRepository:
    """Репозиторий наборов инфляции (%)."""

    def get_by_id(self, inflation_set_id: int) -> Optional[InflationSet]:
        try:
            return InflationSet.objects.select_related("author").get(id=inflation_set_id)
        except InflationSet.DoesNotExist:
            return None

    def list_by_author(self, user) -> list[InflationSet]:
        return list(
            InflationSet.objects.filter(author=user).order_by(
                "-updated_at", "-created_at", "id"
            )
        )

    def create(self, data: dict) -> InflationSet:
        inflation_set = InflationSet.objects.create(**data)
        return InflationSet.objects.select_related("author").get(id=inflation_set.id)

    def update(self, inflation_set_id: int, data: dict) -> Optional[InflationSet]:
        try:
            inflation_set = InflationSet.objects.get(id=inflation_set_id)
        except InflationSet.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(inflation_set, key, value)
        inflation_set.save()
        return InflationSet.objects.select_related("author").get(id=inflation_set.id)

    def delete(self, inflation_set_id: int) -> bool:
        deleted, _ = InflationSet.objects.filter(id=inflation_set_id).delete()
        return deleted > 0


class InflationValueRepository:
    """Репозиторий значений инфляции (%) по годам для набора."""

    def list_by_set(self, inflation_set_id: int):
        return InflationValue.objects.filter(inflation_set_id=inflation_set_id)

    def upsert(self, data: dict) -> InflationValue:
        obj, _created = InflationValue.objects.update_or_create(
            inflation_set=data["inflation_set"],
            year=data["year"],
            defaults={"rate_percent": data["rate_percent"]},
        )
        return obj
