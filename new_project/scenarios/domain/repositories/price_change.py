from scenarios.models import Scenario, ScenarioPriceChangeSetting


class PriceChangeSettingRepository:
    """Репозиторий настроек изменения цен по параметрам сценария."""

    def get_by_scenario(self, scenario_id: int) -> dict[str, str]:
        rows = ScenarioPriceChangeSetting.objects.filter(scenario_id=scenario_id)
        return {row.parameter: row.mode for row in rows}

    def upsert_bulk(self, scenario: Scenario, settings: dict[str, str]) -> None:
        for parameter, mode in settings.items():
            ScenarioPriceChangeSetting.objects.update_or_create(
                scenario=scenario,
                parameter=parameter,
                defaults={"mode": mode},
            )

    def copy_from_scenario(self, source_scenario_id: int, target_scenario: Scenario) -> None:
        source_rows = ScenarioPriceChangeSetting.objects.filter(
            scenario_id=source_scenario_id
        )
        if not source_rows.exists():
            return
        ScenarioPriceChangeSetting.objects.bulk_create(
            [
                ScenarioPriceChangeSetting(
                    scenario=target_scenario,
                    parameter=row.parameter,
                    mode=row.mode,
                )
                for row in source_rows
            ]
        )
