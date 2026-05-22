from __future__ import annotations

from core.models import User
from scenarios.domain.repositories import ScenarioRepository

ERR_SCENARIO_NOT_FOUND = "Сценарий не найден"
ERR_SCENARIO_READ_DENIED = "Нет доступа к этому сценарию"
ERR_SCENARIO_WRITE_DENIED = "Нет прав на изменение этого сценария"
ERR_RESOURCE_READ_DENIED = "Нет прав на использование этого набора"


class ScenarioAccessHelper:
    def __init__(self, scenario_repository: ScenarioRepository | None = None) -> None:
        self._scenario_repository = scenario_repository or ScenarioRepository()
        self._app_settings = None

    def _settings(self):
        if self._app_settings is None:
            from core.domain.services.app_settings import AppSettingsService

            self._app_settings = AppSettingsService()
        return self._app_settings

    def require_scenario_read(self, scenario_id: int, user: User):
        scenario = self._scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, [ERR_SCENARIO_NOT_FOUND]
        if not self._settings().can_read_scenario(
            author_id=scenario.author_id,
            user_id=user.id,
        ):
            return None, [ERR_SCENARIO_READ_DENIED]
        return scenario, []

    def require_scenario_write(self, scenario_id: int, user: User):
        scenario = self._scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return None, [ERR_SCENARIO_NOT_FOUND]
        if not self._settings().can_write_scenario(
            author_id=scenario.author_id,
            user_id=user.id,
        ):
            return None, [ERR_SCENARIO_WRITE_DENIED]
        return scenario, []

    def can_read_resource(self, *, owner_id: int, user: User) -> bool:
        return self._settings().can_read_user_resource(
            owner_id=owner_id,
            user_id=user.id,
        )

    def require_resource_read(self, *, owner_id: int, user: User) -> list[str]:
        if self.can_read_resource(owner_id=owner_id, user=user):
            return []
        return [ERR_RESOURCE_READ_DENIED]

    def shares_all_scenarios(self) -> bool:
        return self._settings().shares_all_scenarios()
