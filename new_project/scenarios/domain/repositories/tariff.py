from typing import Optional

from django.db.models import Case, IntegerField, Max, When

from scenarios.models import (
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)


class TariffRuleRepository:
    def list_by_scenario(self, scenario_id: int) -> list[TariffRule]:
        return list(
            TariffRule.objects.filter(scenario_id=scenario_id)
            .prefetch_related("conditions", "year_values")
            .order_by("position", "id")
        )

    def next_position(self, scenario_id: int) -> int:
        max_pos = (
            TariffRule.objects.filter(scenario_id=scenario_id).aggregate(
                Max("position")
            )["position__max"]
        )
        if max_pos is None:
            return 1
        return int(max_pos) + 1

    def reorder_by_ids(
        self, scenario_id: int, rule_ids: list[int]
    ) -> None:
        """Перезаписывает `position` по переданному порядку."""
        if not rule_ids:
            return

        # Защита от некорректных/чужих id на уровне слоя БД
        # (сервис должен делать валидацию).
        existing_ids = list(
            TariffRule.objects.filter(
                scenario_id=scenario_id, id__in=rule_ids
            ).values_list("id", flat=True)
        )
        if not existing_ids:
            return

        position_by_id = {rid: idx + 1 for idx, rid in enumerate(rule_ids)}

        when_clauses = [
            When(id=rid, then=position_by_id[rid]) for rid in existing_ids
        ]
        TariffRule.objects.filter(
            scenario_id=scenario_id, id__in=existing_ids
        ).update(
            position=Case(
                *when_clauses, output_field=IntegerField()
            )
        )

    def get_by_id(self, rule_id: int) -> Optional[TariffRule]:
        try:
            return (
                TariffRule.objects.select_related("scenario")
                .prefetch_related("conditions", "year_values")
                .get(id=rule_id)
            )
        except TariffRule.DoesNotExist:
            return None

    def create(self, data: dict) -> TariffRule:
        rule = TariffRule.objects.create(**data)
        return (
            TariffRule.objects.select_related("scenario")
            .prefetch_related("conditions", "year_values")
            .get(id=rule.id)
        )

    def update(self, rule_id: int, data: dict) -> Optional[TariffRule]:
        try:
            rule = TariffRule.objects.get(id=rule_id)
        except TariffRule.DoesNotExist:
            return None

        for key, value in data.items():
            setattr(rule, key, value)
        rule.save()
        return (
            TariffRule.objects.select_related("scenario")
            .prefetch_related("conditions", "year_values")
            .get(id=rule.id)
        )

    def delete(self, rule_id: int) -> bool:
        try:
            TariffRule.objects.get(id=rule_id).delete()
            return True
        except TariffRule.DoesNotExist:
            return False

    def replace_conditions(
        self, rule: TariffRule, conditions: list[dict]
    ) -> None:
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
