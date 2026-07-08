from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction

from core.domain.services.app_settings import AppSettingsService
from core.models import User
from scenarios.domain.dto import (
    CreateElasticityRuleDTO,
    ElasticityRuleDTO,
    ElasticitySetDTO,
    ScenarioDTO,
    UpdateElasticityRuleDTO,
)
from scenarios.domain.repositories import (
    ElasticityRuleRepository,
    ElasticitySetRepository,
    ScenarioRepository,
)
from scenarios.domain.services.scenario_access import ScenarioAccessHelper
from scenarios.models import ElasticityRulePoint, ElasticitySet, Scenario


class ElasticityService:
    """Сервис для наборов эластичности и правил с точками маржинальность→коэффициент."""

    def __init__(self):
        self.scenario_repository = ScenarioRepository()
        self.set_repository = ElasticitySetRepository()
        self.rule_repository = ElasticityRuleRepository()
        self._access = ScenarioAccessHelper(self.scenario_repository)

    def _require_set_read(self, elasticity_set: ElasticitySet, user: User) -> list[str]:
        if not self._access.can_read_resource(
            owner_id=elasticity_set.author_id,
            user=user,
        ):
            return ["Нет прав на просмотр этого набора эластичности"]
        return []

    def _require_set_write(self, elasticity_set: ElasticitySet, user: User) -> list[str]:
        if not AppSettingsService().can_write_user_resource(
            owner_id=elasticity_set.author_id,
            user_id=user.id,
        ):
            return ["Нет прав на изменение этого набора эластичности"]
        return []

    def list_sets(self, user: User) -> list[ElasticitySetDTO]:
        if self._access.shares_all_scenarios():
            sets = self.set_repository.list_all()
        else:
            sets = self.set_repository.list_by_author(user)
        return [ElasticitySetDTO.from_model(item) for item in sets]

    @transaction.atomic
    def create_set(
        self, name: str, user: User,
    ) -> tuple[Optional[ElasticitySetDTO], list[str]]:
        if not name or not name.strip():
            return None, ["Название набора обязательно"]

        created = self.set_repository.create({"name": name.strip(), "author": user})
        return ElasticitySetDTO.from_model(created), []

    @transaction.atomic
    def attach_set_to_scenario(
        self, scenario_id: int, elasticity_set_id: int, user: User,
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        scenario, errors = self._access.require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        elasticity_set = self.set_repository.get_by_id(elasticity_set_id)
        if not elasticity_set:
            return None, ["Набор эластичности не найден"]
        errors = self._require_set_read(elasticity_set, user)
        if errors:
            return None, errors

        scenario.elasticity_set = elasticity_set
        scenario.save(update_fields=["elasticity_set"])
        return ScenarioDTO.from_model(scenario), []

    @transaction.atomic
    def delete_set(self, elasticity_set_id: int, user: User) -> tuple[bool, list[str]]:
        elasticity_set = self.set_repository.get_by_id(elasticity_set_id)
        if not elasticity_set:
            return False, ["Набор эластичности не найден"]
        if elasticity_set.author_id != user.id:
            return False, ["Нет прав на удаление этого набора эластичности"]

        Scenario.objects.filter(elasticity_set_id=elasticity_set_id).update(
            elasticity_set=None,
        )
        ok = self.set_repository.delete(elasticity_set_id)
        if not ok:
            return False, ["Ошибка при удалении набора эластичности"]
        return True, []

    def get_attached_overview(
        self, scenario_id: int, user: User,
    ) -> tuple[dict, list[str]]:
        scenario, errors = self._access.require_scenario_read(scenario_id, user)
        if errors:
            return {}, errors

        if not scenario.elasticity_set_id:
            return {"elasticity_set": None, "rules": []}, []

        elasticity_set = scenario.elasticity_set
        rules, errors = self.list_rules(elasticity_set.id, user)
        if errors:
            return {}, errors

        return (
            {
                "elasticity_set": ElasticitySetDTO.from_model(elasticity_set),
                "rules": rules,
            },
            [],
        )

    def list_rules(
        self, elasticity_set_id: int, user: User,
    ) -> tuple[list[ElasticityRuleDTO], list[str]]:
        elasticity_set = self.set_repository.get_by_id(elasticity_set_id)
        if not elasticity_set:
            return [], ["Набор эластичности не найден"]
        errors = self._require_set_read(elasticity_set, user)
        if errors:
            return [], errors

        rules = self.rule_repository.list_by_set(elasticity_set_id)
        return [
            ElasticityRuleDTO.from_model(rule, include_points=False)
            for rule in rules
        ], []

    def get_rule(
        self, rule_id: int, user: User,
    ) -> tuple[Optional[ElasticityRuleDTO], list[str]]:
        rule = self.rule_repository.get_by_id(rule_id)
        if not rule:
            return None, ["Правило эластичности не найдено"]
        errors = self._require_set_read(rule.elasticity_set, user)
        if errors:
            return None, errors
        return ElasticityRuleDTO.from_model(rule, include_points=True), []

    @transaction.atomic
    def create_rule(
        self, dto: CreateElasticityRuleDTO, user: User,
    ) -> tuple[Optional[ElasticityRuleDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        elasticity_set = self.set_repository.get_by_id(dto.elasticity_set_id)
        if not elasticity_set:
            return None, ["Набор эластичности не найден"]
        errors = self._require_set_write(elasticity_set, user)
        if errors:
            return None, errors

        points, point_errors = self._parse_points(dto.points or [])
        if point_errors:
            return None, point_errors

        position = int(dto.position) if dto.position is not None else 0
        rule = self.rule_repository.create(
            {
                "elasticity_set": elasticity_set,
                "name": dto.name.strip(),
                "position": position,
                "cargo_group_id": dto.cargo_group_id,
                "cargo_id": dto.cargo_id or None,
                "message_type_id": dto.message_type_id,
            },
        )
        self.rule_repository.replace_points(rule, points)
        refreshed = self.rule_repository.get_by_id(rule.id)
        return ElasticityRuleDTO.from_model(refreshed, include_points=True), []

    @transaction.atomic
    def update_rule(
        self, rule_id: int, dto: UpdateElasticityRuleDTO, user: User,
    ) -> tuple[Optional[ElasticityRuleDTO], list[str]]:
        rule = self.rule_repository.get_by_id(rule_id)
        if not rule:
            return None, ["Правило эластичности не найдено"]
        errors = self._require_set_write(rule.elasticity_set, user)
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
        if dto.cargo_group_id is not ...:
            update_data["cargo_group_id"] = dto.cargo_group_id
        if dto.cargo_id is not ...:
            update_data["cargo_id"] = dto.cargo_id or None
        if dto.message_type_id is not ...:
            update_data["message_type_id"] = dto.message_type_id

        updated = (
            self.rule_repository.update(rule_id, update_data)
            if update_data
            else rule
        )
        if not updated:
            return None, ["Ошибка при обновлении правила эластичности"]

        if dto.points is not None:
            points, point_errors = self._parse_points(dto.points)
            if point_errors:
                return None, point_errors
            self.rule_repository.replace_points(updated, points)

        refreshed = self.rule_repository.get_by_id(rule_id)
        return ElasticityRuleDTO.from_model(refreshed, include_points=True), []

    @transaction.atomic
    def delete_rule(self, rule_id: int, user: User) -> tuple[bool, list[str]]:
        rule = self.rule_repository.get_by_id(rule_id)
        if not rule:
            return False, ["Правило эластичности не найдено"]
        errors = self._require_set_write(rule.elasticity_set, user)
        if errors:
            return False, errors
        ok = self.rule_repository.delete(rule_id)
        if not ok:
            return False, ["Ошибка при удалении правила эластичности"]
        return True, []

    def _parse_points(self, raw_points: list[dict]) -> tuple[list[dict], list[str]]:
        if not raw_points:
            return [], []

        parsed: list[dict] = []
        seen: set[str] = set()
        for index, raw in enumerate(raw_points):
            marginality_raw = raw.get("marginality")
            coefficient_raw = raw.get("coefficient")
            if marginality_raw is None or str(marginality_raw).strip() == "":
                return [], [f"Строка {index + 1}: маржинальность обязательна"]
            if coefficient_raw is None or str(coefficient_raw).strip() == "":
                return [], [f"Строка {index + 1}: коэффициент обязателен"]
            try:
                marginality = Decimal(str(marginality_raw))
                coefficient = Decimal(str(coefficient_raw))
            except (InvalidOperation, TypeError):
                return [], [f"Строка {index + 1}: некорректный числовой формат"]
            if coefficient < 0:
                return [], [f"Строка {index + 1}: коэффициент не может быть отрицательным"]

            key = format(marginality, "f")
            if key in seen:
                return [], [f"Дублирующаяся маржинальность: {marginality}"]
            seen.add(key)

            point = ElasticityRulePoint(
                marginality=marginality,
                coefficient=coefficient,
            )
            try:
                point.full_clean(exclude=["rule"])
            except Exception:
                return [], [f"Строка {index + 1}: некорректные значения точки"]

            parsed.append(
                {
                    "marginality": point.marginality,
                    "coefficient": point.coefficient,
                },
            )

        parsed.sort(key=lambda item: item["marginality"])
        return parsed, []
