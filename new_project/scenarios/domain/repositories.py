"""
Репозитории для работы с данными сценариев и связанными сущностями.
Инкапсулируют работу с БД, скрывая детали ORM от сервисов.
"""
from typing import Optional

from django.db import transaction
from django.db.models import F

from scenarios.models import (
    Scenario,
    BTDCategory,
    BTDCategoryValue,
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)


class ScenarioRepository:
    """Репозиторий для работы со сценариями."""

    def get_all(self) -> list[Scenario]:
        """Получить все сценарии."""
        return list(Scenario.objects.all().select_related("author"))

    def get_by_id(self, scenario_id: int) -> Optional[Scenario]:
        """Получить сценарий по ID."""
        try:
            return Scenario.objects.select_related("author").get(id=scenario_id)
        except Scenario.DoesNotExist:
            return None

    def get_by_author(self, user) -> list[Scenario]:
        """Получить сценарии автора."""
        return list(Scenario.objects.filter(author=user).select_related("author"))

    def create(self, scenario_data: dict) -> Scenario:
        """Создать сценарий."""
        scenario = Scenario.objects.create(**scenario_data)
        # Перезагружаем с author для консистентности
        return Scenario.objects.select_related("author").get(id=scenario.id)

    def update(self, scenario_id: int, scenario_data: dict) -> Optional[Scenario]:
        """Обновить сценарий."""
        try:
            scenario = Scenario.objects.get(id=scenario_id)
            for key, value in scenario_data.items():
                setattr(scenario, key, value)
            scenario.save()
            return Scenario.objects.select_related("author").get(id=scenario.id)
        except Scenario.DoesNotExist:
            return None

    def delete(self, scenario_id: int) -> bool:
        """Удалить сценарий."""
        try:
            scenario = Scenario.objects.get(id=scenario_id)
            scenario.delete()
            return True
        except Scenario.DoesNotExist:
            return False

    @transaction.atomic
    def copy_scenario(self, source_id: int, new_name: str, new_author) -> Optional[Scenario]:
        """
        Копировать базовые данные сценария.
        Создает новый сценарий на основе существующего.
        
        Копирует только поля модели Scenario:
        - description
        - start_year
        - end_year
        
        В будущем здесь можно добавить копирование связанных данных:
        - связанные модели (ForeignKey, ManyToMany)
        - дочерние объекты
        - параметры и настройки сценария
        """
        source = self.get_by_id(source_id)
        if not source:
            return None

        # Создаем новый сценарий с теми же базовыми данными
        new_scenario = Scenario.objects.create(
            name=new_name,
            description=source.description,
            start_year=source.start_year,
            end_year=source.end_year,
            route_set=source.route_set,
            author=new_author,
        )

        # TODO: Здесь можно добавить копирование связанных данных
        # Например:
        # - new_scenario.related_objects.set(source.related_objects.all())
        # - копирование дочерних объектов через bulk_create

        # Перезагружаем с author
        return Scenario.objects.select_related("author").get(id=new_scenario.id)


class BTDCategoryRepository:
    """Репозиторий для категорий базовых тарифных решений (BTDCategory)."""

    def get_by_id(self, category_id: int) -> Optional[BTDCategory]:
        try:
            return BTDCategory.objects.select_related("scenario").get(id=category_id)
        except BTDCategory.DoesNotExist:
            return None

    def list_by_scenario(self, scenario_id: int):
        """Вернуть категории указанного сценария, отсортированные по позиции."""
        return BTDCategory.objects.filter(scenario_id=scenario_id).order_by("position", "id")

    def create(self, data: dict) -> BTDCategory:
        """
        Создать категорию.
        Если позиция не указана, ставим ее в конец списка для сценария.
        """
        if not data.get("position"):
            last = (
                BTDCategory.objects.filter(scenario=data["scenario"])
                .order_by("-position")
                .first()
            )
            data["position"] = (last.position if last else 0) + 1
        category = BTDCategory.objects.create(**data)
        return category

    def update(self, category_id: int, data: dict) -> Optional[BTDCategory]:
        """Обновить категорию."""
        try:
            category = BTDCategory.objects.get(id=category_id)
        except BTDCategory.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(category, key, value)
        category.save()
        return BTDCategory.objects.select_related("scenario").get(id=category.id)

    def delete(self, category_id: int) -> bool:
        """Удалить категорию."""
        try:
            category = BTDCategory.objects.get(id=category_id)
            category.delete()
            return True
        except BTDCategory.DoesNotExist:
            return False

    def shift_positions_after_delete(self, scenario_id: int, deleted_position: int) -> None:
        """
        Сдвинуть позиции категорий после удаленной позиции на 1 вверх
        в рамках одного сценария.
        """
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
        """
        Создать или обновить значение по (scenario, category, year).
        Ожидает в data: scenario, category, year, value.
        """
        obj, _created = BTDCategoryValue.objects.update_or_create(
            scenario=data["scenario"],
            category=data["category"],
            year=data["year"],
            defaults={"value": data["value"]},
        )
        return obj


class TariffRuleRepository:
    def list_by_scenario(self, scenario_id: int) -> list[TariffRule]:
        return list(
            TariffRule.objects.filter(scenario_id=scenario_id)
            .prefetch_related("conditions", "year_values")
            .order_by("position", "id")
        )

    def get_by_id(self, rule_id: int) -> Optional[TariffRule]:
        try:
            return TariffRule.objects.select_related("scenario").prefetch_related(
                "conditions", "year_values"
            ).get(id=rule_id)
        except TariffRule.DoesNotExist:
            return None

    def create(self, data: dict) -> TariffRule:
        rule = TariffRule.objects.create(**data)
        return TariffRule.objects.select_related("scenario").prefetch_related(
            "conditions", "year_values"
        ).get(id=rule.id)

    def update(self, rule_id: int, data: dict) -> Optional[TariffRule]:
        try:
            rule = TariffRule.objects.get(id=rule_id)
        except TariffRule.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(rule, key, value)
        rule.save()
        return TariffRule.objects.select_related("scenario").prefetch_related(
            "conditions", "year_values"
        ).get(id=rule.id)

    def delete(self, rule_id: int) -> bool:
        try:
            TariffRule.objects.get(id=rule_id).delete()
            return True
        except TariffRule.DoesNotExist:
            return False

    def replace_conditions(self, rule: TariffRule, conditions: list[dict]) -> None:
        TariffRuleCondition.objects.filter(tariff_rule=rule).delete()
        if not conditions:
            return
        TariffRuleCondition.objects.bulk_create(
            [
                TariffRuleCondition(
                    tariff_rule=rule,
                    parameter=c.get("parameter", ""),
                    operator=c.get("operator", "include"),
                    values=c.get("values", []),
                    position=int(c.get("position") or i),
                )
                for i, c in enumerate(conditions)
            ]
        )

    def upsert_year_values(self, rule: TariffRule, year_values: dict) -> None:
        if not year_values:
            return
        for year_str, coef in year_values.items():
            TariffRuleYearValue.objects.update_or_create(
                tariff_rule=rule,
                year=int(year_str),
                defaults={"coefficient": coef},
            )
