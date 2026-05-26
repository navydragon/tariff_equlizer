import os
import sys
import time
from pathlib import Path

import django

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from calculations.domain.services import ScenarioEffectsPandasService, ScenarioEffectsService
from core.models import Route
from scenarios.models import Scenario


def main() -> None:
    scenario = (
        Scenario.objects.select_related("route_set")
        .filter(name__icontains="Базовый")
        .first()
    )
    if scenario is None:
        scenario = Scenario.objects.select_related("route_set").first()
    if scenario is None:
        print("No scenarios found")
        return

    user_id = scenario.author_id
    route_set_id = scenario.route_set_id
    total = Route.objects.filter(route_set_id=route_set_id).count()
    with_charge = Route.objects.filter(
        route_set_id=route_set_id,
        freight_charge_rub__gt=0,
    ).count()
    print(
        f"scenario_id={scenario.id} routes_total={total} with_charge={with_charge}",
    )

    py = ScenarioEffectsService()
    pd = ScenarioEffectsPandasService()

    t0 = time.perf_counter()
    py_result, py_errors = py.compute(scenario=scenario, user_id=user_id)
    t1 = time.perf_counter()
    print(f"python: wall={t1 - t0:.2f}s errors={py_errors}")

    t0 = time.perf_counter()
    pd_result, pd_errors, meta = pd.compute_pandas(scenario=scenario, user_id=user_id)
    t1 = time.perf_counter()
    print(
        f"pandas: wall={t1 - t0:.2f}s "
        f"server_elapsed_ms={meta.get('elapsed_ms')} "
        f"cache_hit={meta.get('cache_hit')} errors={pd_errors}",
    )
    timings = meta.get("timings") or {}
    if timings:
        print(f"  timings: {timings}")

    t0 = time.perf_counter()
    pd_result_2, pd_errors_2, meta_2 = pd.compute_pandas(
        scenario=scenario,
        user_id=user_id,
    )
    t1 = time.perf_counter()
    print(
        f"pandas (repeat): wall={t1 - t0:.2f}s "
        f"server_elapsed_ms={meta_2.get('elapsed_ms')} "
        f"cache_hit={meta_2.get('cache_hit')} errors={pd_errors_2}",
    )

    if py_result and pd_result:
        print(f"baseline python={py_result.baseline_rub} pandas={pd_result.baseline_rub}")


if __name__ == "__main__":
    main()
