import os
import time

import django

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from calculations.domain.services import ScenarioEffectsPandasService, ScenarioEffectsService
from core.models import Route
from scenarios.models import Scenario


def main() -> None:
    scenario = Scenario.objects.filter(name__icontains="Базовый").first()
    if scenario is None:
        scenario = Scenario.objects.first()
    if scenario is None:
        print("No scenarios found")
        return

    user_id = scenario.author_id
    route_set_id = scenario.route_set_id
    total = Route.objects.filter(route_set_id=route_set_id).count()
    with_charge = Route.objects.filter(
        route_set_id=route_set_id,
        freight_charge_ths_rub__gt=0,
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
        f"server_elapsed_ms={meta.get('elapsed_ms')} errors={pd_errors}",
    )

    if py_result and pd_result:
        print(f"baseline python={py_result.baseline_ths_rub} pandas={pd_result.baseline_ths_rub}")


if __name__ == "__main__":
    main()
