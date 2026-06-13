from decimal import Decimal, InvalidOperation
from typing import Literal, Optional

from django.db import transaction

from core.models import User
from scenarios.domain.dto import (
    CreateTariffRuleDTO,
    TariffRuleDTO,
    UpdateTariffRuleDTO,
)
from scenarios.domain.repositories import ScenarioRepository, TariffRuleRepository
from scenarios.domain.services.scenario_access import ScenarioAccessHelper
from calculations.domain.services.scenario_warm_scheduler import (
    schedule_debounced_scenario_warm,
)


ERR_RULE_NOT_FOUND = "Тарифное решение не найдено"


def _schedule_scenario_warm(
    *,
    scenario_id: int,
    change: Literal["create", "update", "delete"],
    rule_id: int | None = None,
    mask_changed: bool = False,
) -> None:
    schedule_debounced_scenario_warm(
        scenario_id=scenario_id,
        change=change,
        rule_id=rule_id,
        mask_changed=mask_changed,
    )


class TariffRuleService:
    def __init__(self):
        self.repository = TariffRuleRepository()
        self.scenario_repository = ScenarioRepository()
        self._access = ScenarioAccessHelper(self.scenario_repository)

    def list_rules(
        self, scenario_id: int, user: User
    ) -> tuple[list[TariffRuleDTO], list[str]]:
        _scenario, errors = self._access.require_scenario_read(scenario_id, user)
        if errors:
            return [], errors
        rules = self.repository.list_by_scenario(scenario_id)
        return [TariffRuleDTO.from_model(r) for r in rules], []

    def get_rule(
        self, rule_id: int, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, [ERR_RULE_NOT_FOUND]
        _scenario, errors = self._access.require_scenario_read(rule.scenario_id, user)
        if errors:
            return None, errors
        return TariffRuleDTO.from_model(rule), []

    @transaction.atomic
    def create_rule(
        self, dto: CreateTariffRuleDTO, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        scenario, errors = self._access.require_scenario_write(dto.scenario_id, user)
        if errors:
            return None, errors

        base_percent = dto.base_percent if dto.base_percent is not None else "100"
        try:
            base_percent_dec = Decimal(str(base_percent))
        except (InvalidOperation, TypeError):
            return None, ["% покрытия базы указан некорректно"]
        if base_percent_dec < 0 or base_percent_dec > 200:
            return None, ["% покрытия базы должен быть в диапазоне 0–200"]

        position = int(dto.position) if dto.position is not None else 0

        rule = self.repository.create(
            {
                "scenario": scenario,
                "name": dto.name.strip(),
                "base_percent": base_percent_dec,
                "position": position,
            }
        )
        if dto.conditions is not None:
            self.repository.replace_conditions(rule, dto.conditions)
        if dto.year_values is not None:
            self._upsert_year_values_checked(
                rule,
                dto.year_values,
                scenario.start_year,
                scenario.end_year,
            )

        refreshed = self.repository.get_by_id(rule.id)
        if refreshed is not None:
            _schedule_scenario_warm(
                scenario_id=scenario.id,
                change="create",
                rule_id=refreshed.id,
                mask_changed=True,
            )
        return TariffRuleDTO.from_model(refreshed), []

    @transaction.atomic
    def update_rule(
        self, rule_id: int, dto: UpdateTariffRuleDTO, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, [ERR_RULE_NOT_FOUND]

        scenario, errors = self._access.require_scenario_write(rule.scenario_id, user)
        if errors:
            return None, errors

        errors = dto.validate()
        if errors:
            return None, errors

        update_data: dict = {}
        if dto.name is not None:
            update_data["name"] = dto.name.strip()
        if dto.position is not None:
            update_data["position"] = int(dto.position)
        if dto.base_percent is not None:
            try:
                base_percent_dec = Decimal(str(dto.base_percent))
            except (InvalidOperation, TypeError):
                return None, ["% покрытия базы указан некорректно"]
            if base_percent_dec < 0 or base_percent_dec > 200:
                return None, ["% покрытия базы должен быть в диапазоне 0–200"]
            update_data["base_percent"] = base_percent_dec

        updated = self.repository.update(rule_id, update_data) if update_data else rule
        if not updated:
            return None, ["Ошибка при обновлении тарифного решения"]

        if dto.conditions is not None:
            self.repository.replace_conditions(updated, dto.conditions)
        if dto.year_values is not None:
            self._upsert_year_values_checked(
                updated,
                dto.year_values,
                scenario.start_year,
                scenario.end_year,
            )

        refreshed = self.repository.get_by_id(rule_id)
        affects_compute = (
            dto.conditions is not None
            or dto.year_values is not None
            or dto.base_percent is not None
            or dto.name is not None
        )
        if refreshed is not None and affects_compute:
            _schedule_scenario_warm(
                scenario_id=scenario.id,
                change="update",
                rule_id=refreshed.id,
                mask_changed=dto.conditions is not None,
            )
        return TariffRuleDTO.from_model(refreshed), []

    @transaction.atomic
    def delete_rule(self, rule_id: int, user: User) -> tuple[bool, list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return False, [ERR_RULE_NOT_FOUND]
        scenario, errors = self._access.require_scenario_write(rule.scenario_id, user)
        if errors:
            return False, errors

        from calculations.domain.services.route_mask_cache import delete_rule_mask
        from calculations.domain.services.tariff_load import TariffLoadService

        scenario_id = rule.scenario_id
        route_set_id = scenario.route_set_id
        conditions = TariffLoadService._rule_conditions_payload(rule)

        ok = self.repository.delete(rule_id)
        if not ok:
            return False, ["Ошибка при удалении тарифного решения"]

        if route_set_id:
            transaction.on_commit(
                lambda: delete_rule_mask(
                    route_set_id=route_set_id,
                    rule_id=rule_id,
                    conditions=conditions,
                ),
            )
        _schedule_scenario_warm(scenario_id=scenario_id, change="delete")
        return True, []

    def _upsert_year_values_checked(
        self, rule, year_values: dict, start_year: int, end_year: int
    ) -> None:
        cleaned: dict = {}
        for year_str, coef in (year_values or {}).items():
            try:
                year = int(year_str)
            except (TypeError, ValueError):
                continue
            if year < start_year or year > end_year:
                continue
            try:
                coef_dec = Decimal(str(coef))
            except (InvalidOperation, TypeError):
                continue
            cleaned[str(year)] = coef_dec
        self.repository.upsert_year_values(rule, cleaned)
