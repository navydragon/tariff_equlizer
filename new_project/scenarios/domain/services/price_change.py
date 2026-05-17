from django.db import transaction

from core.models import User
from scenarios.domain.constants import (
    DEFAULT_PRICE_CHANGE_MODE,
    PRICE_CHANGE_MODE_KEYS,
    PRICE_CHANGE_PARAMETER_KEYS,
    PRICE_CHANGE_PARAMETERS,
)
from scenarios.domain.repositories import PriceChangeSettingRepository, ScenarioRepository


class PriceChangeSettingService:
    """Сервис настроек изменения цен по параметрам экономики маршрута."""

    def __init__(self):
        self.repository = PriceChangeSettingRepository()
        self.scenario_repository = ScenarioRepository()

    def get_settings(self, scenario_id: int) -> dict[str, str]:
        stored = self.repository.get_by_scenario(scenario_id)
        return {
            key: stored.get(key, DEFAULT_PRICE_CHANGE_MODE)
            for key, _ in PRICE_CHANGE_PARAMETERS
        }

    @transaction.atomic
    def save_settings(
        self,
        scenario_id: int,
        settings: dict[str, str],
        user: User,
    ) -> list[str]:
        scenario = self.scenario_repository.get_by_id(scenario_id)
        if not scenario:
            return ["Сценарий не найден"]
        if scenario.author != user:
            return ["Нет прав на изменение этого сценария"]

        errors = self._validate_settings(settings)
        if errors:
            return errors

        normalized = {
            key: settings[key]
            for key, _ in PRICE_CHANGE_PARAMETERS
        }
        self.repository.upsert_bulk(scenario, normalized)
        return []

    @staticmethod
    def _validate_settings(settings: dict[str, str]) -> list[str]:
        if not isinstance(settings, dict):
            return ["Некорректный формат настроек изменения цен"]

        unknown_keys = set(settings.keys()) - PRICE_CHANGE_PARAMETER_KEYS
        if unknown_keys:
            return [f"Неизвестный параметр: {', '.join(sorted(unknown_keys))}"]

        missing_keys = PRICE_CHANGE_PARAMETER_KEYS - set(settings.keys())
        if missing_keys:
            return ["Необходимо указать режим для всех параметров изменения цен"]

        for key, mode in settings.items():
            if mode not in PRICE_CHANGE_MODE_KEYS:
                return [f"Некорректный режим для параметра «{key}»"]

        return []
