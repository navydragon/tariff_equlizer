from typing import Optional

from django.db import transaction

from scenarios.domain.repositories.price_change import PriceChangeSettingRepository
from scenarios.models import Scenario


class ScenarioRepository:
    """Репозиторий для работы со сценариями."""

    def get_all(self) -> list[Scenario]:
        return list(Scenario.objects.all().select_related("author"))

    def get_by_id(self, scenario_id: int) -> Optional[Scenario]:
        try:
            return Scenario.objects.select_related("author").get(id=scenario_id)
        except Scenario.DoesNotExist:
            return None

    def get_by_author(self, user) -> list[Scenario]:
        return list(Scenario.objects.filter(author=user).select_related("author"))

    def create(self, scenario_data: dict) -> Scenario:
        scenario = Scenario.objects.create(**scenario_data)
        return Scenario.objects.select_related("author").get(id=scenario.id)

    def update(self, scenario_id: int, scenario_data: dict) -> Optional[Scenario]:
        try:
            scenario = Scenario.objects.get(id=scenario_id)
        except Scenario.DoesNotExist:
            return None

        for key, value in scenario_data.items():
            setattr(scenario, key, value)
        scenario.save()
        return Scenario.objects.select_related("author").get(id=scenario.id)

    def delete(self, scenario_id: int) -> bool:
        try:
            Scenario.objects.get(id=scenario_id).delete()
            return True
        except Scenario.DoesNotExist:
            return False

    @transaction.atomic
    def copy_scenario(self, source_id: int, new_name: str, new_author) -> Optional[Scenario]:
        source = self.get_by_id(source_id)
        if not source:
            return None

        new_scenario = Scenario.objects.create(
            name=new_name,
            description=source.description,
            start_year=source.start_year,
            end_year=source.end_year,
            route_set=source.route_set,
            exchange_rate_set=source.exchange_rate_set,
            inflation_set=source.inflation_set,
            author=new_author,
        )
        PriceChangeSettingRepository().copy_from_scenario(source_id, new_scenario)
        return Scenario.objects.select_related("author").get(id=new_scenario.id)

