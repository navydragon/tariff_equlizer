from typing import Optional

from scenarios.models import TariffRule, TariffRuleCondition, TariffRuleYearValue


class TariffRuleRepository:
    def list_by_scenario(self, scenario_id: int) -> list[TariffRule]:
        return list(
            TariffRule.objects.filter(scenario_id=scenario_id)
            .prefetch_related("conditions", "year_values")
            .order_by("position", "id")
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

