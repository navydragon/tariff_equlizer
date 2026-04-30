from typing import Optional

from django.db.models import F

from scenarios.models import BTDCategory, BTDCategoryValue


class BTDCategoryRepository:
    """Репозиторий для категорий базовых тарифных решений (BTDCategory)."""

    def get_by_id(self, category_id: int) -> Optional[BTDCategory]:
        try:
            return BTDCategory.objects.select_related("scenario").get(id=category_id)
        except BTDCategory.DoesNotExist:
            return None

    def list_by_scenario(self, scenario_id: int):
        return BTDCategory.objects.filter(scenario_id=scenario_id).order_by("position", "id")

    def create(self, data: dict) -> BTDCategory:
        if not data.get("position"):
            last = (
                BTDCategory.objects.filter(scenario=data["scenario"])
                .order_by("-position")
                .first()
            )
            data["position"] = (last.position if last else 0) + 1
        return BTDCategory.objects.create(**data)

    def update(self, category_id: int, data: dict) -> Optional[BTDCategory]:
        try:
            category = BTDCategory.objects.get(id=category_id)
        except BTDCategory.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(category, key, value)
        category.save()
        return BTDCategory.objects.select_related("scenario").get(id=category.id)

    def delete(self, category_id: int) -> bool:
        try:
            BTDCategory.objects.get(id=category_id).delete()
            return True
        except BTDCategory.DoesNotExist:
            return False

    def shift_positions_after_delete(self, scenario_id: int, deleted_position: int) -> None:
        BTDCategory.objects.filter(
            scenario_id=scenario_id,
            position__gt=deleted_position,
        ).update(position=F("position") - 1)


class BTDCategoryValueRepository:
    """Репозиторий для значений категорий базовых тарифных решений."""

    def get_by_scenario_and_category_and_year(
        self,
        scenario_id: int,
        category_id: int,
        year: int,
    ) -> Optional[BTDCategoryValue]:
        try:
            return BTDCategoryValue.objects.get(
                scenario_id=scenario_id,
                category_id=category_id,
                year=year,
            )
        except BTDCategoryValue.DoesNotExist:
            return None

    def list_by_scenario(self, scenario_id: int):
        return BTDCategoryValue.objects.filter(scenario_id=scenario_id)

    def upsert(self, data: dict) -> BTDCategoryValue:
        obj, _created = BTDCategoryValue.objects.update_or_create(
            scenario=data["scenario"],
            category=data["category"],
            year=data["year"],
            defaults={"value": data["value"]},
        )
        return obj

