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
ERR_RULES_REORDER_INVALID = "Некорректный список правил"
ERR_RULES_REORDER_INCOMPLETE = "Нужно передать все правила сценария"
ERR_RULES_REORDER_DUPLICATES = "В списке правил есть дубликаты"


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

        position = (
            int(dto.position) if dto.position is not None else self.repository.next_position(scenario.id)
        )
        is_enabled = dto.is_enabled if dto.is_enabled is not None else True

        rule = self.repository.create(
            {
                "scenario": scenario,
                "name": dto.name.strip(),
                "base_percent": base_percent_dec,
                "position": position,
                "is_enabled": is_enabled,
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
    def reorder_rules(
        self,
        scenario_id: int,
        rule_ids: list[int],
        user: User,
    ) -> tuple[Optional[list[TariffRuleDTO]], list[str]]:
        scenario, errors = self._access.require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        if not rule_ids:
            return None, [ERR_RULES_REORDER_INVALID]

        if len(set(rule_ids)) != len(rule_ids):
            return None, [ERR_RULES_REORDER_DUPLICATES]

        all_rules = self.repository.list_by_scenario(scenario_id)
        all_ids = {r.id for r in all_rules}
        if set(rule_ids) != all_ids or len(rule_ids) != len(all_ids):
            return None, [ERR_RULES_REORDER_INCOMPLETE]

        for rid in rule_ids:
            if rid not in all_ids:
                return None, [ERR_RULES_REORDER_INVALID]

        self.repository.reorder_by_ids(scenario_id=scenario.id, rule_ids=rule_ids)
        refreshed_rules = self.repository.list_by_scenario(scenario.id)
        return ([TariffRuleDTO.from_model(r) for r in refreshed_rules], [])

    @transaction.atomic
    def move_rule(
        self,
        rule_id: int,
        direction: str,
        user: User,
    ) -> tuple[Optional[list[TariffRuleDTO]], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, [ERR_RULE_NOT_FOUND]

        scenario_id = rule.scenario_id
        scenario, errors = self._access.require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        ordered_rules = self.repository.list_by_scenario(scenario_id)
        ordered_ids = [r.id for r in ordered_rules]

        idx = ordered_ids.index(rule_id) if rule_id in ordered_ids else -1
        if idx < 0:
            return None, [ERR_RULE_NOT_FOUND]

        if direction == "up":
            if idx == 0:
                return None, ["Уже на первой позиции"]
            ordered_ids[idx - 1], ordered_ids[idx] = ordered_ids[idx], ordered_ids[idx - 1]
        elif direction == "down":
            if idx == len(ordered_ids) - 1:
                return None, ["Уже на последней позиции"]
            ordered_ids[idx], ordered_ids[idx + 1] = ordered_ids[idx + 1], ordered_ids[idx]
        else:
            return None, ["Неверный direction: ожидается up или down"]

        self.repository.reorder_by_ids(scenario_id=scenario.id, rule_ids=ordered_ids)
        refreshed_rules = self.repository.list_by_scenario(scenario.id)
        return ([TariffRuleDTO.from_model(r) for r in refreshed_rules], [])

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
        if dto.is_enabled is not None:
            update_data["is_enabled"] = bool(dto.is_enabled)

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

    @transaction.atomic
    def set_rule_enabled(
        self, rule_id: int, is_enabled: bool, user: User
    ) -> tuple[Optional[TariffRuleDTO], list[str]]:
        rule = self.repository.get_by_id(rule_id)
        if not rule:
            return None, [ERR_RULE_NOT_FOUND]

        scenario, errors = self._access.require_scenario_write(rule.scenario_id, user)
        if errors:
            return None, errors

        if bool(rule.is_enabled) == bool(is_enabled):
            return TariffRuleDTO.from_model(rule), []

        updated = self.repository.update(rule_id, {"is_enabled": bool(is_enabled)})
        if not updated:
            return None, ["Ошибка при обновлении тарифного решения"]

        refreshed = self.repository.get_by_id(rule_id)
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
