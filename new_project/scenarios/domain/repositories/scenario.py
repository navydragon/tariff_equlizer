from typing import Optional

from django.db import transaction

from scenarios.domain.repositories.price_change import PriceChangeSettingRepository
from scenarios.models import (
    BTDCategory,
    BTDCategoryValue,
    Scenario,
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)


class ScenarioRepository:
    """Репозиторий для работы со сценариями."""

    def get_all(self) -> list[Scenario]:
        return list(Scenario.objects.all().select_related("author"))

    def get_by_id(self, scenario_id: int) -> Optional[Scenario]:
        try:
            return Scenario.objects.select_related("author").get(id=scenario_id)
        except Scenario.DoesNotExist:
            return None

    def get_by_author(self, user) -> list[Scenario]:
        return list(Scenario.objects.filter(author=user).select_related("author"))

    def create(self, scenario_data: dict) -> Scenario:
        scenario = Scenario.objects.create(**scenario_data)
        return Scenario.objects.select_related("author").get(id=scenario.id)

    def update(self, scenario_id: int, scenario_data: dict) -> Optional[Scenario]:
        try:
            scenario = Scenario.objects.get(id=scenario_id)
        except Scenario.DoesNotExist:
            return None

        for key, value in scenario_data.items():
            setattr(scenario, key, value)
        scenario.save()
        return Scenario.objects.select_related("author").get(id=scenario.id)

    def delete(self, scenario_id: int) -> bool:
        try:
            Scenario.objects.get(id=scenario_id).delete()
            return True
        except Scenario.DoesNotExist:
            return False

    @transaction.atomic
    def copy_scenario(self, source_id: int, new_name: str, new_author) -> Optional[Scenario]:
        source = self.get_by_id(source_id)
        if not source:
            return None

        new_scenario = Scenario.objects.create(
            name=new_name,
            description=source.description,
            start_year=source.start_year,
            end_year=source.end_year,
            route_set=source.route_set,
            exchange_rate_set=source.exchange_rate_set,
            inflation_set=source.inflation_set,
            elasticity_set=source.elasticity_set,
            export_price_mode=source.export_price_mode,
            include_base_tariff_decisions=source.include_base_tariff_decisions,
            consider_turnover_changes=source.consider_turnover_changes,
            consider_enterprise_load=source.consider_enterprise_load,
            retention_coefficient_mode=source.retention_coefficient_mode,
            author=new_author,
        )
        PriceChangeSettingRepository().copy_from_scenario(source_id, new_scenario)
        self._copy_btd(source, new_scenario)
        self._copy_tariff_rules(source, new_scenario)
        return Scenario.objects.select_related("author").get(id=new_scenario.id)

    @staticmethod
    def _copy_btd(source: Scenario, target: Scenario) -> None:
        category_map: dict[int, int] = {}
        for category in BTDCategory.objects.filter(scenario=source).order_by(
            "position", "id"
        ):
            new_category = BTDCategory.objects.create(
                name=category.name,
                scenario=target,
                position=category.position,
            )
            category_map[category.id] = new_category.id

        value_rows = []
        for value in BTDCategoryValue.objects.filter(scenario=source):
            new_category_id = category_map.get(value.category_id)
            if new_category_id is None:
                continue
            value_rows.append(
                BTDCategoryValue(
                    scenario=target,
                    category_id=new_category_id,
                    year=value.year,
                    value=value.value,
                )
            )
        if value_rows:
            BTDCategoryValue.objects.bulk_create(value_rows)

    @staticmethod
    def _copy_tariff_rules(source: Scenario, target: Scenario) -> None:
        rules = (
            TariffRule.objects.filter(scenario=source)
            .prefetch_related("conditions", "year_values")
            .order_by("position", "id")
        )
        for rule in rules:
            new_rule = TariffRule.objects.create(
                scenario=target,
                name=rule.name,
                base_percent=rule.base_percent,
                position=rule.position,
            )
            conditions = [
                TariffRuleCondition(
                    tariff_rule=new_rule,
                    parameter=condition.parameter,
                    operator=condition.operator,
                    values=condition.values,
                    position=condition.position,
                )
                for condition in rule.conditions.all()
            ]
            if conditions:
                TariffRuleCondition.objects.bulk_create(conditions)

            year_values = [
                TariffRuleYearValue(
                    tariff_rule=new_rule,
                    year=year_value.year,
                    coefficient=year_value.coefficient,
                )
                for year_value in rule.year_values.all()
            ]
            if year_values:
                TariffRuleYearValue.objects.bulk_create(year_values)

        from calculations.domain.services.scenario_effects_warm import (
            warm_scenario_after_rule_change,
        )

        transaction.on_commit(
            lambda target_id=target.id: warm_scenario_after_rule_change(
                scenario_id=target_id,
                change="create",
                mask_changed=False,
            ),
        )
