from __future__ import annotations

import logging
from typing import Literal

from core.domain.repositories.setting import SettingRepository

logger = logging.getLogger(__name__)

SHARE_SCENARIOS_CODE = "share_scenarios"
SHARE_MODE_ALL = "all"
SHARE_MODE_OWN = "own"
DEFAULT_SHARE_MODE = SHARE_MODE_ALL

ERR_SCENARIO_READ_DENIED = "Нет доступа к этому сценарию"
ERR_RESOURCE_READ_DENIED = "Нет доступа к этому набору"


class AppSettingsService:
    def __init__(self) -> None:
        self._repository = SettingRepository()

    def get_value(self, code: str, default: str = "") -> str:
        setting = self._repository.get_by_code(code)
        if setting is None:
            return default
        return setting.value.strip()

    def get_share_scenarios_mode(self) -> Literal["all", "own"]:
        raw = self.get_value(SHARE_SCENARIOS_CODE, default=DEFAULT_SHARE_MODE).lower()
        if raw == SHARE_MODE_ALL:
            return SHARE_MODE_ALL
        if raw == SHARE_MODE_OWN:
            return SHARE_MODE_OWN
        logger.warning(
            "Неизвестное значение %s=%r, используется %s",
            SHARE_SCENARIOS_CODE,
            raw,
            SHARE_MODE_OWN,
        )
        return SHARE_MODE_OWN

    def shares_all_scenarios(self) -> bool:
        return self.get_share_scenarios_mode() == SHARE_MODE_ALL

    @staticmethod
    def can_read_user_resource(*, owner_id: int, user_id: int) -> bool:
        if owner_id == user_id:
            return True
        return AppSettingsService().shares_all_scenarios()

    @staticmethod
    def can_write_user_resource(*, owner_id: int, user_id: int) -> bool:
        # Временно: правка любых сценариев/наборов без проверки автора.
        return True

    def can_read_scenario(self, *, author_id: int, user_id: int) -> bool:
        return self.can_read_user_resource(owner_id=author_id, user_id=user_id)

    def can_write_scenario(self, *, author_id: int, user_id: int) -> bool:
        return self.can_write_user_resource(owner_id=author_id, user_id=user_id)
