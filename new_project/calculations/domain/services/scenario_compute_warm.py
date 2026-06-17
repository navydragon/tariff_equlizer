from __future__ import annotations

import time
from collections.abc import Callable

from calculations.domain.services.scenario_compute_store import try_load_scenario_compute
from calculations.domain.services.scenario_effects_cache import compute_scenario_data_version
from calculations.domain.services.scenario_effects_pandas import ScenarioEffectsPandasService
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario


def wait_for_compact_on_disk(
    *,
    scenario_id: int,
    data_version: str,
    timeout_s: float,
    poll_interval_s: float = 0.5,
) -> tuple[bool, int]:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        bundle = try_load_scenario_compute(
            scenario_id=scenario_id,
            data_version=data_version,
        )
        if bundle is not None and bundle.compact is not None:
            return True, int((time.perf_counter() - started) * 1000)
        time.sleep(poll_interval_s)
    return False, int((time.perf_counter() - started) * 1000)


def warm_scenario_compute(
    *,
    route_set_id: int | None = None,
    scenario_id: int | None = None,
    compact_timeout_s: float = 180.0,
    write: Callable[[str], None] | None = None,
) -> int:
    """Прогревает KPI и compact на диске. Возвращает число неуспешных сценариев."""
    if write is None:
        write = print

    scenarios = _scenarios_to_warm(
        route_set_id=route_set_id,
        scenario_id=scenario_id,
    )
    if not scenarios:
        write("Нет сценариев для прогрева.")
        return 0

    pandas_service = ScenarioEffectsPandasService()
    tariff_load = TariffLoadService()
    write(f"==> Прогреваем scenario_compute для {len(scenarios)} сценариев")

    failed = 0
    for scenario in scenarios:
        if not scenario.author_id:
            write(f"    [{scenario.id}] {scenario.name} — нет author_id, пропуск")
            continue

        context = tariff_load.build_scenario_context(scenario)
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=context.base_coef_by_year,
            rules=context.rules,
        )
        started = time.perf_counter()
        _result, errors, meta = pandas_service.compute_pandas(
            scenario=scenario,
            user_id=scenario.author_id,
        )
        kpi_ms = int((time.perf_counter() - started) * 1000)
        if errors:
            write(f"    [{scenario.id}] {scenario.name} — KPI ошибки: {errors}")
            failed += 1
            continue

        compact_ready = bool(meta.get("compact_ready"))
        compact_wait_ms = 0
        if not compact_ready:
            compact_ready, compact_wait_ms = wait_for_compact_on_disk(
                scenario_id=scenario.id,
                data_version=data_version,
                timeout_s=compact_timeout_s,
            )

        if compact_ready:
            write(
                f"    [{scenario.id}] {scenario.name} — "
                f"kpi={kpi_ms} ms, compact_wait={compact_wait_ms} ms",
            )
        else:
            write(
                f"    [{scenario.id}] {scenario.name} — "
                f"timeout compact ({compact_timeout_s:.0f} s)",
            )
            failed += 1

    return failed


def _scenarios_to_warm(
    *,
    route_set_id: int | None,
    scenario_id: int | None,
) -> list[Scenario]:
    qs = Scenario.objects.select_related("route_set", "author").order_by("id")
    if scenario_id is not None:
        return [qs.get(pk=scenario_id)]
    assert route_set_id is not None
    return list(qs.filter(route_set_id=route_set_id))
