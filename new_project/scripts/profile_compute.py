import os
import sys
import time

import django

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from calculations.domain.services.scenario_effects_pandas import ScenarioEffectsPandasService
from calculations.domain.services.scenario_effects import ScenarioEffectsService
from calculations.domain.services.scenario_effects_cache import store_payload, make_cache_key
from calculations.domain.services.tariff_load import TariffLoadService
from core.models import Route
from scenarios.models import Scenario


def profile_pandas(scenario, user_id):
    svc = ScenarioEffectsPandasService()
    tariff = TariffLoadService()

    t0 = time.perf_counter()
    context = tariff.build_scenario_context(scenario)
    t1 = time.perf_counter()

    df, skipped_charge, skipped_volume = svc._load_routes_df(scenario)
    t2 = time.perf_counter()

    compact, global_totals = svc._compute_compact(df, context, context.years)
    t3 = time.perf_counter()

    from calculations.domain.services.scenario_effects_formatting import build_cards_from_totals

    cards = build_cards_from_totals(global_totals, context.years)
    filter_options = svc._collect_filter_options(df)
    t4 = time.perf_counter()

    cache_key = make_cache_key(user_id=user_id, scenario_id=scenario.id)
    from calculations.domain.services.scenario_effects_cache import ScenarioEffectsCachePayload

    store_payload(
        cache_key=cache_key,
        payload=ScenarioEffectsCachePayload(
            user_id=user_id,
            scenario_id=scenario.id,
            years=context.years,
            routes_without_charge=skipped_charge,
            routes_without_volume=skipped_volume,
            baseline_total=global_totals.baseline_total,
            facts=[],
            compact=compact,
        ),
    )
    t5 = time.perf_counter()

    print(f"  context: {t1 - t0:.2f}s")
    print(f"  load_df ({len(df)} rows): {t2 - t1:.2f}s")
    print(f"  compute_compact: {t3 - t2:.2f}s")
    print(f"  cards+filters: {t4 - t3:.2f}s")
    print(f"  cache_store: {t5 - t4:.2f}s")
    print(f"  TOTAL pandas profile: {t5 - t0:.2f}s")
    print(f"  holdings in filter_options: {len(filter_options['holdings'])}")


def main():
    scenario = Scenario.objects.filter(name__icontains="Базовый").first() or Scenario.objects.first()
    user_id = scenario.author_id
    rs = scenario.route_set_id
    total = Route.objects.filter(route_set_id=rs).count()
    with_charge = Route.objects.filter(route_set_id=rs, freight_charge_ths_rub__gt=0).count()
    print(f"scenario={scenario.id} total={total} with_charge={with_charge}\n")

    print("PYTHON:")
    t0 = time.perf_counter()
    ScenarioEffectsService().compute(scenario=scenario, user_id=user_id)
    print(f"  wall: {time.perf_counter() - t0:.2f}s\n")

    print("PANDAS breakdown:")
    profile_pandas(scenario, user_id)


if __name__ == "__main__":
    main()
