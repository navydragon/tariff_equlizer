from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction

from core.models import User
from scenarios.domain.dto import (
    InflationSetDTO,
    InflationValueDTO,
    ScenarioDTO,
    UpdateInflationValueDTO,
)
from scenarios.domain.repositories import (
    InflationSetRepository,
    InflationValueRepository,
    ScenarioRepository,
)
from core.domain.services.app_settings import AppSettingsService
from scenarios.domain.services.scenario_access import ScenarioAccessHelper
from scenarios.models import InflationSet, InflationValue, Scenario


class InflationService:
    """Сервис для работы с наборами инфляции и значениями (%) по годам."""

    def __init__(self):
        self.scenario_repository = ScenarioRepository()
        self.set_repository = InflationSetRepository()
        self.value_repository = InflationValueRepository()
        self._access = ScenarioAccessHelper(self.scenario_repository)

    def _require_scenario_read(self, scenario_id: int, user: User):
        return self._access.require_scenario_read(scenario_id, user)

    def _require_scenario_write(self, scenario_id: int, user: User):
        return self._access.require_scenario_write(scenario_id, user)

    def list_sets(self, user: User) -> list[InflationSetDTO]:
        if self._access.shares_all_scenarios():
            sets = self.set_repository.list_all()
        else:
            sets = self.set_repository.list_by_author(user)
        return [InflationSetDTO.from_model(s) for s in sets]

    @transaction.atomic
    def create_set(
        self, name: str, user: User
    ) -> tuple[Optional[InflationSetDTO], list[str]]:
        if not name or not name.strip():
            return None, ["Название набора обязательно"]

        created = self.set_repository.create({"name": name.strip(), "author": user})
        return InflationSetDTO.from_model(created), []

    @transaction.atomic
    def attach_set_to_scenario(
        self, scenario_id: int, inflation_set_id: int, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        scenario, errors = self._require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        inflation_set = self.set_repository.get_by_id(inflation_set_id)
        if not inflation_set:
            return None, ["Набор инфляции не найден"]
        if not self._access.can_read_resource(
            owner_id=inflation_set.author_id,
            user=user,
        ):
            return None, ["Нет прав на использование этого набора инфляции"]

        scenario.inflation_set = inflation_set
        scenario.save(update_fields=["inflation_set"])
        return ScenarioDTO.from_model(scenario), []

    def get_matrix(self, scenario_id: int, user: User) -> tuple[dict, list[str]]:
        scenario, errors = self._require_scenario_read(scenario_id, user)
        if errors:
            return {}, errors

        if not scenario.inflation_set_id:
            return {"years": [], "inflation_set": None, "values": {}}, []

        inflation_set = scenario.inflation_set
        years = list(range(scenario.start_year, scenario.end_year + 1))

        values = list(self.value_repository.list_by_set(inflation_set.id))
        value_map: dict[str, str] = {
            str(v.year): str(v.rate_percent) for v in values
        }

        return (
            {
                "years": years,
                "inflation_set": InflationSetDTO.from_model(inflation_set),
                "values": value_map,
            },
            [],
        )

    @transaction.atomic
    def update_value(
        self, dto: UpdateInflationValueDTO, user: User
    ) -> tuple[Optional[InflationValueDTO], list[str]]:
        basic_errors = dto.validate_basic()
        if basic_errors:
            return None, basic_errors

        scenario, errors = self._require_scenario_write(dto.scenario_id, user)
        if errors:
            return None, errors

        if not (scenario.start_year <= dto.year <= scenario.end_year):
            return None, [
                "Год должен быть в пределах сценария "
                f"{scenario.start_year}-{scenario.end_year}"
            ]

        inflation_set = self.set_repository.get_by_id(dto.inflation_set_id)
        if not inflation_set:
            return None, ["Набор инфляции не найден"]
        if not AppSettingsService().can_write_user_resource(
            owner_id=inflation_set.author_id,
            user_id=user.id,
        ):
            return None, ["Нет прав на изменение этого набора инфляции"]

        try:
            dec = Decimal(str(dto.rate_percent))
        except (InvalidOperation, TypeError):
            return None, ["Некорректный формат значения"]

        try:
            value_obj = InflationValue(
                inflation_set=inflation_set,
                year=dto.year,
                rate_percent=dec,
            )
            value_obj.full_clean(exclude=["inflation_set", "year"])
        except Exception:
            return None, ["Некорректный формат значения"]

        saved = self.value_repository.upsert(
            {
                "inflation_set": inflation_set,
                "year": dto.year,
                "rate_percent": value_obj.rate_percent,
            }
        )
        return InflationValueDTO.from_model(saved), []

    @transaction.atomic
    def delete_set(self, inflation_set_id: int, user: User) -> tuple[bool, list[str]]:
        inflation_set = self.set_repository.get_by_id(inflation_set_id)
        if not inflation_set:
            return False, ["Набор инфляции не найден"]
        if inflation_set.author_id != user.id:
            return False, ["Нет прав на удаление этого набора инфляции"]

        Scenario.objects.filter(inflation_set_id=inflation_set_id).update(
            inflation_set=None
        )

        ok = self.set_repository.delete(inflation_set_id)
        if not ok:
            return False, ["Ошибка при удалении набора инфляции"]
        return True, []
