from __future__ import annotations

import sys
import threading
from typing import Iterable

from django.conf import settings
from django.db import transaction

from calculations.domain.services.route_effects_loader import (
    fetch_routes_dataframe_cached_timed,
)
from calculations.domain.services.route_mart_store import (
    get_route_mart_refs_version,
)
from calculations.domain.services.route_mart_warm_status import (
    init_route_mart_warm_status,
    mark_route_mart_warm_error,
    update_route_mart_warm_status,
)
from core.models import Route, RouteSet
from scenarios.models import Scenario

DEBOUNCE_SECONDS = 0.5
_RUNNING_TESTS = any(arg == "test" for arg in sys.argv)

_timers: dict[int, threading.Timer] = {}
_pending: dict[int, int] = {}
_guard = threading.Lock()


def _prime_route_mart_warm_status(*, route_set_id: int) -> None:
    refs_version = get_route_mart_refs_version()
    init_route_mart_warm_status(
        route_set_id=route_set_id,
        refs_version=refs_version,
        phase="queued",
    )


def _schedule_scenario_rebuilds_for_route_set(*, route_set_id: int) -> None:
    from calculations.domain.services.scenario_warm_scheduler import (
        schedule_scenario_compute_rebuild,
    )

    scenario_ids = Scenario.objects.filter(
        route_set_id=route_set_id,
    ).values_list("id", flat=True)
    for scenario_id in scenario_ids:
        schedule_scenario_compute_rebuild(scenario_id=int(scenario_id))


def warm_route_mart(*, route_set_id: int) -> None:
    refs_version = get_route_mart_refs_version()
    update_route_mart_warm_status(
        route_set_id=route_set_id,
        refs_version=refs_version,
        phase="building",
        error=None,
    )
    try:
        fetch_routes_dataframe_cached_timed(
            route_set_id,
            prewarm_masks=True,
        )
        update_route_mart_warm_status(
            route_set_id=route_set_id,
            refs_version=refs_version,
            phase="done",
            error=None,
        )
        _schedule_scenario_rebuilds_for_route_set(route_set_id=route_set_id)
    except Exception as exc:  # noqa: BLE001
        mark_route_mart_warm_error(route_set_id=route_set_id, error=str(exc))


def schedule_debounced_route_mart_warm(*, route_set_id: int) -> None:
    if route_set_id <= 0:
        return
    if bool(getattr(settings, "DISABLE_AUTO_WARM", False)):
        return

    if _RUNNING_TESTS:
        def _run_in_tests() -> None:
            _prime_route_mart_warm_status(route_set_id=route_set_id)
            warm_route_mart(route_set_id=route_set_id)

        transaction.on_commit(_run_in_tests)
        return

    def _fire() -> None:
        with _guard:
            target_route_set_id = _pending.pop(route_set_id, None)
            _timers.pop(route_set_id, None)
        if target_route_set_id is None:
            return
        warm_route_mart(route_set_id=target_route_set_id)

    def _schedule_timer() -> None:
        _prime_route_mart_warm_status(route_set_id=route_set_id)
        with _guard:
            _pending[route_set_id] = route_set_id
            existing = _timers.pop(route_set_id, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, _fire)
            timer.daemon = True
            _timers[route_set_id] = timer
            timer.start()

    transaction.on_commit(_schedule_timer)


def schedule_route_mart_warm_for_all() -> None:
    route_set_ids = (
        Route.objects.order_by()
        .values_list("route_set_id", flat=True)
        .distinct()
    )
    for route_set_id in route_set_ids:
        if route_set_id:
            schedule_debounced_route_mart_warm(route_set_id=int(route_set_id))


def schedule_route_mart_warm_many(*, route_set_ids: Iterable[int]) -> None:
    seen: set[int] = set()
    for route_set_id in route_set_ids:
        normalized = int(route_set_id)
        if normalized <= 0 or normalized in seen:
            continue
        seen.add(normalized)
        schedule_debounced_route_mart_warm(route_set_id=normalized)


def schedule_route_mart_warm_by_route_set(*, route_set_id: int | None) -> None:
    if route_set_id is None:
        schedule_route_mart_warm_for_all()
        return
    try:
        exists = RouteSet.objects.filter(pk=route_set_id).exists()
    except Exception:  # noqa: BLE001
        exists = False
    if exists:
        schedule_debounced_route_mart_warm(route_set_id=route_set_id)
