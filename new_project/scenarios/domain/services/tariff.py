from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction

from core.models import User
from scenarios.domain.dto import (
    CreateTariffRuleDTO,
    TariffRuleDTO,
    UpdateTariffRuleDTO,
)
from scenarios.domain.repositories import ScenarioRepository, TariffRuleRepository
from scenarios.domain.services.scenario_access import ScenarioAccessHelper


ERR_RULE_NOT_FOUND = "Тарифное решение не найдено"


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
        return TariffRuleDTO.from_model(refreshed), []

    def delete_rule(self, rule_id: int, user: User) -> tuple[bool, list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return False, [ERR_RULE_NOT_FOUND]
        _scenario, errors = self._access.require_scenario_write(rule.scenario_id, user)
        if errors:
            return False, errors
        ok = self.repository.delete(rule_id)
        return (True, []) if ok else (False, ["Ошибка при удалении тарифного решения"])

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
