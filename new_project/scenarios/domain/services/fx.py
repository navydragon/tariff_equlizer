from decimal import Decimal, InvalidOperation
from typing import Optional

from django.db import transaction

from core.models import User
from scenarios.domain.dto import (
    ExchangeRateSetDTO,
    ExchangeRateValueDTO,
    ScenarioDTO,
    UpdateExchangeRateValueDTO,
)
from scenarios.domain.repositories import (
    ExchangeRateSetRepository,
    ExchangeRateValueRepository,
    ScenarioRepository,
)
from core.domain.services.app_settings import AppSettingsService
from scenarios.domain.services.scenario_access import ScenarioAccessHelper
from scenarios.models import ExchangeRateSet, ExchangeRateValue, Scenario


class ExchangeRateService:
    """Сервис для работы с наборами курсов валют и значениями USD/RUB по годам."""

    def __init__(self):
        self.scenario_repository = ScenarioRepository()
        self.set_repository = ExchangeRateSetRepository()
        self.value_repository = ExchangeRateValueRepository()
        self._access = ScenarioAccessHelper(self.scenario_repository)

    def _require_scenario_read(self, scenario_id: int, user: User):
        return self._access.require_scenario_read(scenario_id, user)

    def _require_scenario_write(self, scenario_id: int, user: User):
        return self._access.require_scenario_write(scenario_id, user)

    def list_sets(self, user: User) -> list[ExchangeRateSetDTO]:
        if self._access.shares_all_scenarios():
            sets = self.set_repository.list_all()
        else:
            sets = self.set_repository.list_by_author(user)
        return [ExchangeRateSetDTO.from_model(s) for s in sets]

    @transaction.atomic
    def create_set(
        self, name: str, user: User
    ) -> tuple[Optional[ExchangeRateSetDTO], list[str]]:
        if not name or not name.strip():
            return None, ["Название набора обязательно"]

        created = self.set_repository.create({"name": name.strip(), "author": user})
        return ExchangeRateSetDTO.from_model(created), []

    @transaction.atomic
    def attach_set_to_scenario(
        self, scenario_id: int, rate_set_id: int, user: User
    ) -> tuple[Optional[ScenarioDTO], list[str]]:
        scenario, errors = self._require_scenario_write(scenario_id, user)
        if errors:
            return None, errors

        rate_set = self.set_repository.get_by_id(rate_set_id)
        if not rate_set:
            return None, ["Набор курсов валют не найден"]
        if not self._access.can_read_resource(owner_id=rate_set.author_id, user=user):
            return None, ["Нет прав на использование этого набора курсов"]

        scenario.exchange_rate_set = rate_set
        scenario.save(update_fields=["exchange_rate_set"])
        return ScenarioDTO.from_model(scenario), []

    def get_matrix(self, scenario_id: int, user: User) -> tuple[dict, list[str]]:
        scenario, errors = self._require_scenario_read(scenario_id, user)
        if errors:
            return {}, errors

        if not scenario.exchange_rate_set_id:
            return {"years": [], "rate_set": None, "values": {}}, []

        rate_set = scenario.exchange_rate_set
        years = list(range(scenario.start_year, scenario.end_year + 1))

        values = list(self.value_repository.list_by_set(rate_set.id))
        value_map: dict[str, str] = {str(v.year): str(v.usd_rub) for v in values}

        return (
            {
                "years": years,
                "rate_set": ExchangeRateSetDTO.from_model(rate_set),
                "values": value_map,
            },
            [],
        )

    @transaction.atomic
    def update_value(
        self, dto: UpdateExchangeRateValueDTO, user: User
    ) -> tuple[Optional[ExchangeRateValueDTO], list[str]]:
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

        rate_set = self.set_repository.get_by_id(dto.rate_set_id)
        if not rate_set:
            return None, ["Набор курсов валют не найден"]
        if not AppSettingsService().can_write_user_resource(
            owner_id=rate_set.author_id,
            user_id=user.id,
        ):
            return None, ["Нет прав на изменение этого набора курсов"]

        try:
            dec = Decimal(str(dto.usd_rub))
        except (InvalidOperation, TypeError):
            return None, ["Некорректный формат значения"]

        # Валидация decimal_places/max_digits через модель.
        try:
            value_obj = ExchangeRateValue(rate_set=rate_set, year=dto.year, usd_rub=dec)
            value_obj.full_clean(exclude=["rate_set", "year"])
        except Exception:
            return None, ["Некорректный формат значения"]

        saved = self.value_repository.upsert(
            {"rate_set": rate_set, "year": dto.year, "usd_rub": value_obj.usd_rub}
        )
        return ExchangeRateValueDTO.from_model(saved), []

    @transaction.atomic
    def delete_set(self, rate_set_id: int, user: User) -> tuple[bool, list[str]]:
        rate_set = self.set_repository.get_by_id(rate_set_id)
        if not rate_set:
            return False, ["Набор курсов валют не найден"]
        if rate_set.author_id != user.id:
            return False, ["Нет прав на удаление этого набора курсов"]

        Scenario.objects.filter(exchange_rate_set_id=rate_set_id).update(
            exchange_rate_set=None
        )

        ok = self.set_repository.delete(rate_set_id)
        if not ok:
            return False, ["Ошибка при удалении набора курсов"]
        return True, []
