from __future__ import annotations

import sys
import threading
from typing import Literal

from django.db import transaction

DEBOUNCE_SECONDS = 0.5
_RUNNING_TESTS = any(arg == "test" for arg in sys.argv)

_timers: dict[int, threading.Timer] = {}
_pending: dict[int, dict] = {}
_guard = threading.Lock()


def schedule_debounced_scenario_warm(
    *,
    scenario_id: int,
    change: Literal["create", "update", "delete"],
    rule_id: int | None = None,
    mask_changed: bool = False,
) -> None:
    kwargs = {
        "scenario_id": scenario_id,
        "change": change,
        "rule_id": rule_id,
        "mask_changed": mask_changed,
    }

    if _RUNNING_TESTS:
        from calculations.domain.services.scenario_effects_warm import (
            warm_scenario_after_rule_change,
        )

        transaction.on_commit(
            lambda: warm_scenario_after_rule_change(**kwargs),
        )
        return

    def _fire() -> None:
        with _guard:
            job_kwargs = _pending.pop(scenario_id, None)
            _timers.pop(scenario_id, None)
        if not job_kwargs:
            return
        from calculations.domain.services.scenario_effects_warm import (
            warm_scenario_after_rule_change,
        )

        warm_scenario_after_rule_change(**job_kwargs)

    def _schedule_timer() -> None:
        with _guard:
            _pending[scenario_id] = kwargs
            existing = _timers.pop(scenario_id, None)
            if existing is not None:
                existing.cancel()
            timer = threading.Timer(DEBOUNCE_SECONDS, _fire)
            timer.daemon = True
            _timers[scenario_id] = timer
            timer.start()

    transaction.on_commit(_schedule_timer)
