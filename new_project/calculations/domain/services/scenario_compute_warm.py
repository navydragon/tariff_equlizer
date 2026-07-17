from __future__ import annotations

import time
from collections.abc import Callable

from calculations.domain.services.scenario_compute_store import (
    is_scenario_compact_on_disk,
    is_scenario_fallout_on_disk,
    purge_scenario_compute,
    try_load_scenario_compute,
)
from calculations.domain.services.scenario_effects_cache import compute_scenario_data_version
from calculations.domain.services.scenario_effects_pandas import ScenarioEffectsPandasService
from calculations.domain.services.scenario_effects_warm import warm_scenario_kpi_snapshot
from calculations.domain.services.scenario_warm_status import (
    clear_warm_status,
    get_warm_status,
    resolve_warm_data_version,
)
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


def wait_scenario_detail_ready(
    *,
    scenario_id: int,
    data_version: str,
    wait_fallout: bool,
    timeout_s: float,
    poll_interval_s: float = 2.0,
) -> tuple[bool, bool, int]:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        warm_status = get_warm_status(scenario_id=scenario_id)
        if warm_status and warm_status.get("phase") == "error":
            elapsed_ms = int((time.perf_counter() - started) * 1000)
            return False, False, elapsed_ms

        compact_ready = is_scenario_compact_on_disk(
            scenario_id=scenario_id,
            data_version=data_version,
        )
        fallout_ready = (
            is_scenario_fallout_on_disk(
                scenario_id=scenario_id,
                data_version=data_version,
            )
            if wait_fallout
            else True
        )
        if compact_ready and fallout_ready:
            return True, fallout_ready, int((time.perf_counter() - started) * 1000)
        time.sleep(poll_interval_s)

    compact_ready = is_scenario_compact_on_disk(
        scenario_id=scenario_id,
        data_version=data_version,
    )
    fallout_ready = (
        is_scenario_fallout_on_disk(
            scenario_id=scenario_id,
            data_version=data_version,
        )
        if wait_fallout
        else True
    )
    elapsed_ms = int((time.perf_counter() - started) * 1000)
    return compact_ready, fallout_ready, elapsed_ms


def warm_scenario_compute(
    *,
    route_set_id: int | None = None,
    scenario_id: int | None = None,
    compact_timeout_s: float = 180.0,
    force: bool = False,
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

    if force:
        write(
            f"==> Принудительно пересобираем scenario_compute для {len(scenarios)} сценариев",
        )
    else:
        write(f"==> Прогреваем scenario_compute для {len(scenarios)} сценариев")

    failed = 0
    for scenario in scenarios:
        if force:
            if _force_rebuild_single_scenario(
                scenario,
                compact_timeout_s=compact_timeout_s,
                write=write,
            ):
                failed += 1
            continue

        if not scenario.author_id:
            write(f"    [{scenario.id}] {scenario.name} — нет author_id, пропуск")
            continue

        failed += int(
            _warm_single_scenario_from_cache(
                scenario,
                compact_timeout_s=compact_timeout_s,
                write=write,
            ),
        )

    return failed


def _force_rebuild_single_scenario(
    scenario: Scenario,
    *,
    compact_timeout_s: float,
    write: Callable[[str], None],
) -> bool:
    write(f"    [{scenario.id}] {scenario.name} — сброс кеша и warm-статуса")
    purge_scenario_compute(scenario_id=scenario.id)
    clear_warm_status(scenario_id=scenario.id)

    started = time.perf_counter()
    warm_scenario_kpi_snapshot(scenario_id=scenario.id)
    kpi_ms = int((time.perf_counter() - started) * 1000)

    data_version = resolve_warm_data_version(scenario_id=scenario.id)
    if not data_version:
        write(f"    [{scenario.id}] {scenario.name} — data_version не определён")
        return True

    warm_status = get_warm_status(scenario_id=scenario.id)
    if warm_status and warm_status.get("phase") == "error":
        error = warm_status.get("error") or "ошибка пересчёта KPI"
        write(f"    [{scenario.id}] {scenario.name} — {error}")
        return True

    wait_fallout = bool(
        getattr(scenario, "consider_demand_elasticity", False)
        and getattr(scenario, "elasticity_set_id", None)
    )
    compact_ready, fallout_ready, detail_wait_ms = wait_scenario_detail_ready(
        scenario_id=scenario.id,
        data_version=data_version,
        wait_fallout=wait_fallout,
        timeout_s=compact_timeout_s,
    )

    warm_status = get_warm_status(scenario_id=scenario.id)
    if warm_status and warm_status.get("phase") == "error":
        error = warm_status.get("error") or "Ошибка фоновой сборки детализации"
        write(f"    [{scenario.id}] {scenario.name} — {error}")
        return True

    if not compact_ready or (wait_fallout and not fallout_ready):
        write(
            f"    [{scenario.id}] {scenario.name} — "
            f"timeout compact/fallout ({compact_timeout_s:.0f} s)",
        )
        return True

    write(
        f"    [{scenario.id}] {scenario.name} — "
        f"kpi={kpi_ms} ms, compact_wait={detail_wait_ms} ms",
    )
    return False


def _warm_single_scenario_from_cache(
    scenario: Scenario,
    *,
    compact_timeout_s: float,
    write: Callable[[str], None],
) -> bool:
    if not scenario.author_id:
        write(f"    [{scenario.id}] {scenario.name} — нет author_id, пропуск")
        return True

    pandas_service = ScenarioEffectsPandasService()
    tariff_load = TariffLoadService()
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
        return True

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
        return False

    write(
        f"    [{scenario.id}] {scenario.name} — "
        f"timeout compact ({compact_timeout_s:.0f} s)",
    )
    return True


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
