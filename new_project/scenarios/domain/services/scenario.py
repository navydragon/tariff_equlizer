from typing import Optional

from django.db import transaction

from core.models import RouteSet, User
from scenarios.domain.dto import (
    CreateScenarioDTO,
    ScenarioDTO,
    ScenarioListDTO,
    UpdateScenarioDTO,
)
from scenarios.domain.repositories import ScenarioRepository
from scenarios.domain.services.price_change import PriceChangeSettingService
from scenarios.domain.services.scenario_access import (
    ERR_SCENARIO_NOT_FOUND,
    ScenarioAccessHelper,
)
from scenarios.models import ExchangeRateSet


def _schedule_scenario_compute_warm(*, scenario_id: int) -> None:
    from calculations.domain.services.scenario_warm_scheduler import (
        schedule_scenario_compute_rebuild,
    )

    schedule_scenario_compute_rebuild(scenario_id=scenario_id)


def _compute_affecting_update(
    scenario,
    update_data: dict,
    *,
    route_set_changed: bool,
) -> bool:
    if route_set_changed:
        return True
    compute_fields = (
        "start_year",
        "end_year",
        "consider_turnover_changes",
        "consider_demand_elasticity",
        "consider_enterprise_load",
        "retention_coefficient_mode",
    )
    return any(
        field in update_data and getattr(scenario, field) != update_data[field]
        for field in compute_fields
    )


class ScenarioService:
    """Сервис для работы со сценариями."""

    def __init__(self):
        self.repository = ScenarioRepository()
        self.price_change_service = PriceChangeSettingService()
        self._access = ScenarioAccessHelper(self.repository)

    def _app_settings(self):
        from core.domain.services.app_settings import AppSettingsService

        return AppSettingsService()

    def get_user_scenarios(self, user: User) -> list[ScenarioListDTO]:
        if self._app_settings().shares_all_scenarios():
            scenarios = self.repository.get_all()
        else:
            scenarios = self.repository.get_by_author(user)
        return [ScenarioListDTO.from_model(s) for s in scenarios]

    def get_scenario(self, scenario_id: int) -> Optional[ScenarioDTO]:
        scenario = self.repository.get_by_id(scenario_id)
        if not scenario:
            return None
        settings = self.price_change_service.get_settings(scenario_id)
        return ScenarioDTO.from_model(scenario, price_change_settings=settings)

    def _scenario_dto(self, scenario) -> ScenarioDTO:
        settings = self.price_change_service.get_settings(scenario.id)
        return ScenarioDTO.from_model(scenario, price_change_settings=settings)

    @transaction.atomic
    def create_scenario(
        self, dto: CreateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        scenario = self.repository.create(
            {
                "name": dto.name,
                "description": dto.description,
                "start_year": dto.start_year,
                "end_year": dto.end_year,
                "author": user,
            }
        )
        return self._scenario_dto(scenario), []

    @transaction.atomic
    def create_scenario_from_base(
        self, dto: CreateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        if not dto.base_scenario_id:
            return None, ["Не указан базовый сценарий"]

        errors = dto.validate()
        if errors:
            return None, errors

        base_scenario = self.repository.get_by_id(dto.base_scenario_id)
        if not base_scenario:
            return None, ["Исходный сценарий не найден"]
        if not self._app_settings().can_read_scenario(
            author_id=base_scenario.author_id,
            user_id=user.id,
        ):
            return None, ["Исходный сценарий не найден"]

        scenario = self.repository.copy_scenario(
            source_id=dto.base_scenario_id,
            new_name=dto.name,
            new_author=user,
        )
        if not scenario:
            return None, ["Исходный сценарий не найден"]

        update_data: dict = {}
        if dto.name:
            update_data["name"] = dto.name
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.start_year is not None:
            update_data["start_year"] = dto.start_year
        if dto.end_year is not None:
            update_data["end_year"] = dto.end_year

        if update_data:
            updated_scenario = self.repository.update(scenario.id, update_data)
            if updated_scenario:
                scenario = updated_scenario

        return self._scenario_dto(scenario), []

    def update_scenario(
        self, scenario_id: int, dto: UpdateScenarioDTO, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        scenario, errors = self._access.require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        errors = dto.validate()
        if errors:
            return None, errors

        update_data: dict = {}
        if dto.name is not None:
            update_data["name"] = dto.name
        if dto.description is not None:
            update_data["description"] = dto.description
        if dto.start_year is not None:
            update_data["start_year"] = dto.start_year
        if dto.end_year is not None:
            update_data["end_year"] = dto.end_year
        if dto.include_base_tariff_decisions is not None:
            update_data["include_base_tariff_decisions"] = dto.include_base_tariff_decisions
        if dto.consider_turnover_changes is not None:
            update_data["consider_turnover_changes"] = dto.consider_turnover_changes
        if dto.consider_demand_elasticity is not None:
            update_data["consider_demand_elasticity"] = dto.consider_demand_elasticity
        if dto.consider_enterprise_load is not None:
            update_data["consider_enterprise_load"] = dto.consider_enterprise_load
        if dto.retention_coefficient_mode is not None:
            update_data["retention_coefficient_mode"] = dto.retention_coefficient_mode

        route_set, errors = self._get_route_set(dto.route_set_id)
        if errors:
            return None, errors
        route_set_changed = route_set is not None and scenario.route_set_id != route_set.id
        if route_set is not None:
            update_data["route_set"] = route_set

        rate_set, errors = self._get_exchange_rate_set(
            exchange_rate_set_id=dto.exchange_rate_set_id,
            user=user,
        )
        if errors:
            return None, errors
        if rate_set is not None:
            update_data["exchange_rate_set"] = rate_set

        if dto.export_price_mode is not None:
            update_data["export_price_mode"] = dto.export_price_mode

        updated_scenario = self.repository.update(scenario_id, update_data)
        if not updated_scenario:
            return None, ["Ошибка при обновлении сценария"]

        if _compute_affecting_update(
            scenario,
            update_data,
            route_set_changed=route_set_changed,
        ):
            _schedule_scenario_compute_warm(scenario_id=scenario_id)

        if dto.price_change_settings is not None:
            price_errors = self.price_change_service.save_settings(
                scenario_id,
                dto.price_change_settings,
                user,
            )
            if price_errors:
                return None, price_errors

        return self._scenario_dto(updated_scenario), []

    @staticmethod
    def _get_route_set(route_set_id: Optional[int]) -> tuple[Optional[RouteSet], list[str]]:
        if route_set_id is None:
            return None, []
        try:
            return RouteSet.objects.get(id=route_set_id), []
        except RouteSet.DoesNotExist:
            return None, ["Набор маршрутов не найден"]

    @staticmethod
    def _get_exchange_rate_set(
        exchange_rate_set_id: Optional[int],
        user: User,
    ) -> tuple[Optional[ExchangeRateSet], list[str]]:
        if exchange_rate_set_id is None:
            return None, []
        try:
            rate_set = ExchangeRateSet.objects.get(id=exchange_rate_set_id)
        except ExchangeRateSet.DoesNotExist:
            return None, ["Набор курсов валют не найден"]
        if not self._app_settings().can_read_user_resource(
            owner_id=rate_set.author_id,
            user_id=user.id,
        ):
            return None, ["Нет прав на использование этого набора курсов"]
        return rate_set, []

    def delete_scenario(
        self, scenario_id: int, user: User
    ) -> tuple[bool, list[str]]:
        scenario = self.repository.get_by_id(scenario_id)
        if not scenario:
            return False, [ERR_SCENARIO_NOT_FOUND]
        if scenario.author != user:
            return False, ["Нет прав на удаление этого сценария"]
        if user.active_scenario_id == scenario_id:
            return False, [
                "Нельзя удалить активный сценарий. "
                "Сначала выберите другой активный сценарий."
            ]

        success = self.repository.delete(scenario_id)
        return (
            (True, [])
            if success
            else (False, ["Ошибка при удалении сценария"])
        )

    def set_active_scenario(
        self, user: User, scenario_id: Optional[int]
    ) -> tuple[bool, list[str]]:
        if scenario_id is not None:
            scenario, errors = self._access.require_scenario_read(scenario_id, user)
            if errors:
                return False, errors

        user.active_scenario_id = scenario_id
        user.save(update_fields=["active_scenario"])
        return True, []
