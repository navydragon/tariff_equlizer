"""
Бенчмарк кэшей и расчётов отдельных тарифных правил (1–10 правил).

Примеры:
  python scripts/benchmark_tariff_rules.py
  python scripts/benchmark_tariff_rules.py --rules-count 5 --clear-cache
  python scripts/benchmark_tariff_rules.py --profile warm --scenario-id 1
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path

import django

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

from django.core.cache import cache
from django.db import transaction

from calculations.domain.dto.scenario_effects import ScenarioEffectsAggregateRequestDTO
from calculations.domain.services.route_mask_cache import build_or_load_rule_mask
from calculations.domain.services.route_mart_store import (
    load_mart_meta,
    resolve_mart_parquet_path,
    load_mart_sidecar_dataframe,
    route_mart_cache_root,
)
from calculations.domain.services.route_mask_cache import route_mask_cache_root
from calculations.domain.services.scenario_compute_store import (
    scenario_compute_cache_root,
    try_load_scenario_compute,
)
from calculations.domain.services.scenario_effects_cache import (
    compute_scenario_data_version,
    get_payload,
)
from calculations.domain.services.scenario_effects_compute import rule_specs_from_context
from calculations.domain.services.scenario_effects_pandas import ScenarioEffectsPandasService
from calculations.domain.services.scenario_effects import ScenarioEffectsService
from calculations.domain.services.tariff_load import TariffLoadService
from core.management.commands.refresh_deploy_caches import clear_all_deploy_caches
from core.models import MessageType, RailRoad, Route, Shipper, ShipmentType, WagonKind
from scenarios.domain.dto import CreateTariffRuleDTO, UpdateTariffRuleDTO
from scenarios.domain.services import TariffRuleService
from scenarios.models import Scenario, TariffRule

BENCH_PREFIX = "BENCH-"
COMPACT_POLL_TIMEOUT_S = 120.0
COMPACT_POLL_INTERVAL_S = 0.5


@dataclass
class RulePreset:
    name: str
    parameter: str | None
    operator: str
    values: list | str | int | None
    base_percent: str
    year_values: dict[str, str]


@dataclass
class BenchmarkRun:
    rules_count: int
    profile: str
    cold_compute_ms: int | None = None
    warm_compute_ms: int | None = None
    compact_ready_ms: int | None = None
    compact_ready: bool | None = None
    masks_ms_cold: int | None = None
    masks_ms_warm: int | None = None
    rule_by_year_ms: int | None = None
    scenario_compute_cache_hit: bool | None = None
    burst_create_ms: int | None = None
    update_coef_ms: int | None = None
    update_conditions_ms: int | None = None
    aggregate_pending_ms: int | None = None
    aggregate_ready_ms: int | None = None
    matched_routes: list[int] = field(default_factory=list)
    rules_by_year_2030: str | None = None
    errors: list[str] = field(default_factory=list)


def _dir_size_mb(root: Path) -> float:
    if not root.is_dir():
        return 0.0
    total = sum(f.stat().st_size for f in root.rglob("*") if f.is_file())
    return round(total / (1024 * 1024), 2)


def _cache_sizes() -> dict[str, float]:
    return {
        "route_masks_mb": _dir_size_mb(route_mask_cache_root()),
        "scenario_compute_mb": _dir_size_mb(scenario_compute_cache_root()),
        "route_mart_mb": _dir_size_mb(route_mart_cache_root()),
    }


def _resolve_scenario(scenario_id: int | None) -> Scenario:
    if scenario_id:
        return Scenario.objects.select_related("route_set", "author").get(pk=scenario_id)
    scenario = (
        Scenario.objects.select_related("route_set", "author")
        .filter(name__icontains="Базовый")
        .first()
    )
    if scenario is None:
        scenario = Scenario.objects.select_related("route_set", "author").first()
    if scenario is None:
        raise SystemExit("No scenarios found")
    return scenario


def _sample_values() -> dict[str, object]:
    wagon = WagonKind.objects.filter(name__icontains="цист").first() or WagonKind.objects.first()
    message = MessageType.objects.first()
    shipment = ShipmentType.objects.first()
    railroad = RailRoad.objects.first()
    shipper = Shipper.objects.first()
    holding = (
        Shipper.objects.exclude(holding="")
        .exclude(holding__isnull=True)
        .values_list("holding", flat=True)
        .first()
    )
    return {
        "wagon_kind_id": str(wagon.id) if wagon else "1",
        "cargo_group_code": "8",
        "message_type_id": str(message.id) if message else "1",
        "shipment_type_id": str(shipment.id) if shipment else "1",
        "railroad_code": str(railroad.code) if railroad else "01",
        "shipper_id": str(shipper.id) if shipper else "1",
        "holding": holding or "Прочие",
        "distance_belt_lt": 500,
        "distance_belt_include": "0-500",
    }


def _build_presets(samples: dict[str, object]) -> list[RulePreset]:
    return [
        RulePreset("wagon_kind", "wagon_kind", "include", [samples["wagon_kind_id"]], "100", {"2030": "2.0000"}),
        RulePreset("cargo_group", "cargo_group", "include", [samples["cargo_group_code"]], "100", {"2026": "1.1000"}),
        RulePreset("message_type", "message_type", "include", [samples["message_type_id"]], "100", {"2027": "1.2000"}),
        RulePreset("shipment_type", "shipment_type", "include", [samples["shipment_type_id"]], "50", {"2028": "1.3000"}),
        RulePreset("origin_railroad", "origin_railroad", "include", [samples["railroad_code"]], "100", {"2029": "1.4000"}),
        RulePreset("shipper", "shipper", "include", [samples["shipper_id"]], "100", {"2031": "1.5000"}),
        RulePreset("holding", "shipper_holding", "include", [samples["holding"]], "100", {"2032": "1.6000"}),
        RulePreset("distance_lt", "distance_belt", "lt", samples["distance_belt_lt"], "100", {"2033": "1.7000"}),
        RulePreset("distance_include", "distance_belt", "include", [samples["distance_belt_include"]], "100", {"2034": "1.8000"}),
        RulePreset("all_routes", None, "include", None, "100", {"2035": "1.9000"}),
    ]


def _delete_bench_rules(scenario_id: int) -> int:
    qs = TariffRule.objects.filter(scenario_id=scenario_id, name__startswith=BENCH_PREFIX)
    count = qs.count()
    qs.delete()
    return count


def _create_rules(
    *,
    service: TariffRuleService,
    user,
    scenario: Scenario,
    presets: list[RulePreset],
    count: int,
) -> list[int]:
    rule_ids: list[int] = []
    for index in range(count):
        preset = presets[index]
        conditions = []
        if preset.parameter:
            conditions.append(
                {
                    "parameter": preset.parameter,
                    "operator": preset.operator,
                    "values": preset.values,
                },
            )
        dto = CreateTariffRuleDTO(
            scenario_id=scenario.id,
            name=f"{BENCH_PREFIX}{preset.name}",
            base_percent=preset.base_percent,
            position=index + 1,
            conditions=conditions,
            year_values=preset.year_values,
        )
        created, errors = service.create_rule(dto, user)
        if errors or created is None:
            raise RuntimeError(f"create_rule failed: {errors}")
        rule_ids.append(created.id)
    return rule_ids


def _wait_compact(*, scenario_id: int, data_version: str, timeout_s: float) -> tuple[bool, int]:
    started = time.perf_counter()
    while time.perf_counter() - started < timeout_s:
        bundle = try_load_scenario_compute(
            scenario_id=scenario_id,
            data_version=data_version,
        )
        if bundle is not None and bundle.compact is not None:
            return True, int((time.perf_counter() - started) * 1000)
        time.sleep(COMPACT_POLL_INTERVAL_S)
    return False, int((time.perf_counter() - started) * 1000)


def _matched_routes_per_rule(scenario: Scenario) -> list[int]:
    tl = TariffLoadService()
    ctx = tl.build_scenario_context(scenario)
    specs = rule_specs_from_context(tl, ctx)
    bench_specs = [s for s in specs if s.name.startswith(BENCH_PREFIX)]
    parquet = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
    if not parquet.is_file():
        return []
    df, _ = load_mart_sidecar_dataframe(parquet, include_charge=True)
    meta = load_mart_meta(parquet)
    return [
        int(
            build_or_load_rule_mask(
                route_set_id=scenario.route_set_id,
                rule_id=spec.id,
                conditions=spec.conditions,
                df=df,
                mart_meta=meta,
            ).sum(),
        )
        for spec in bench_specs
    ]


def _run_for_count(
    *,
    scenario: Scenario,
    user,
    presets: list[RulePreset],
    count: int,
    profile: str,
    clear_cache: bool,
) -> BenchmarkRun:
    run = BenchmarkRun(rules_count=count, profile=profile)
    service = TariffRuleService()
    pandas_service = ScenarioEffectsPandasService()
    effects_service = ScenarioEffectsService()
    user_id = user.id

    try:
        if clear_cache or profile == "cold":
            clear_all_deploy_caches()
        _delete_bench_rules(scenario.id)

        t_burst = time.perf_counter()
        rule_ids = _create_rules(
            service=service,
            user=user,
            scenario=scenario,
            presets=presets,
            count=count,
        )
        run.burst_create_ms = int((time.perf_counter() - t_burst) * 1000)

        scenario = Scenario.objects.select_related("route_set").get(pk=scenario.id)
        run.matched_routes = _matched_routes_per_rule(scenario)

        tl = TariffLoadService()
        ctx = tl.build_scenario_context(scenario)
        data_version = compute_scenario_data_version(
            scenario=scenario,
            base_coef_by_year=ctx.base_coef_by_year,
            rules=ctx.rules,
        )

        t0 = time.perf_counter()
        result, errors, meta = pandas_service.compute_pandas(
            scenario=scenario,
            user_id=user_id,
        )
        run.cold_compute_ms = int((time.perf_counter() - t0) * 1000)
        if errors:
            run.errors.extend(errors)
        if meta:
            timings = meta.get("timings") or {}
            run.masks_ms_cold = timings.get("masks_ms")
            run.scenario_compute_cache_hit = meta.get("scenario_compute_cache_hit")
            run.compact_ready = meta.get("compact_ready")
            if result and result.cards:
                for card in result.cards:
                    if card.year == 2030:
                        run.rules_by_year_2030 = card.rules_bln

        if not run.compact_ready:
            ready, wait_ms = _wait_compact(
                scenario_id=scenario.id,
                data_version=data_version,
                timeout_s=COMPACT_POLL_TIMEOUT_S,
            )
            run.compact_ready = ready
            run.compact_ready_ms = wait_ms
            if not ready:
                run.errors.append("compact_ready timeout")

        if profile in ("warm", "mixed"):
            t1 = time.perf_counter()
            _result2, errors2, meta2 = pandas_service.compute_pandas(
                scenario=scenario,
                user_id=user_id,
            )
            run.warm_compute_ms = int((time.perf_counter() - t1) * 1000)
            if errors2:
                run.errors.extend(errors2)
            if meta2:
                timings2 = meta2.get("timings") or {}
                run.masks_ms_warm = timings2.get("masks_ms")
                run.rule_by_year_ms = timings2.get("rule_by_year_ms")
                run.scenario_compute_cache_hit = meta2.get("scenario_compute_cache_hit")

        if rule_ids:
            t_coef = time.perf_counter()
            dto = UpdateTariffRuleDTO(year_values={"2030": "2.5000"})
            with transaction.atomic():
                service.update_rule(rule_ids[0], dto, user)
            run.update_coef_ms = int((time.perf_counter() - t_coef) * 1000)

            t_cond = time.perf_counter()
            dto2 = UpdateTariffRuleDTO(
                conditions=[
                    {
                        "parameter": "wagon_kind",
                        "operator": "include",
                        "values": [_sample_values()["wagon_kind_id"]],
                    },
                ],
            )
            with transaction.atomic():
                service.update_rule(rule_ids[0], dto2, user)
            run.update_conditions_ms = int((time.perf_counter() - t_cond) * 1000)

        _result3, errors3, meta3 = pandas_service.compute_pandas(
            scenario=scenario,
            user_id=user_id,
        )
        if errors3:
            run.errors.extend(errors3)
        cache_key = _result3.cache_key if _result3 else None
        if cache_key:
            agg_req = ScenarioEffectsAggregateRequestDTO(
                cache_key=cache_key,
                year=2030,
                group_by="cargo_group",
            )
            t_agg = time.perf_counter()
            agg_result, agg_errors = effects_service.aggregate(
                scenario=scenario,
                user_id=user_id,
                request=agg_req,
            )
            run.aggregate_ready_ms = int((time.perf_counter() - t_agg) * 1000)
            if agg_errors:
                run.aggregate_pending_ms = run.aggregate_ready_ms
                run.errors.extend(agg_errors)
            elif agg_result is None:
                run.errors.append("aggregate returned None")

    except Exception as exc:
        run.errors.append(str(exc))
    finally:
        _delete_bench_rules(scenario.id)

    return run


def main() -> None:
    parser = argparse.ArgumentParser(description="Benchmark tariff rules caches")
    parser.add_argument("--scenario-id", type=int, default=None)
    parser.add_argument("--rules-count", type=int, default=None, help="1-10, default all")
    parser.add_argument("--clear-cache", action="store_true")
    parser.add_argument(
        "--profile",
        choices=["cold", "warm", "mixed"],
        default="mixed",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="JSON report path",
    )
    args = parser.parse_args()

    scenario = _resolve_scenario(args.scenario_id)
    user = scenario.author
    if user is None:
        from django.contrib.auth import get_user_model

        user = get_user_model().objects.first()
    if user is None:
        raise SystemExit("No user for benchmark")

    route_set_id = scenario.route_set_id
    routes_total = Route.objects.filter(route_set_id=route_set_id).count() if route_set_id else 0

    samples = _sample_values()
    presets = _build_presets(samples)
    counts = (
        [args.rules_count]
        if args.rules_count
        else list(range(1, min(11, len(presets) + 1)))
    )

    print(
        f"scenario_id={scenario.id} name={scenario.name!r} "
        f"routes={routes_total} profile={args.profile}",
    )

    runs: list[dict] = []
    for count in counts:
        if count < 1 or count > 10:
            print(f"skip rules_count={count}")
            continue
        print(f"--- rules_count={count} ---")
        run = _run_for_count(
            scenario=scenario,
            user=user,
            presets=presets,
            count=count,
            profile=args.profile,
            clear_cache=args.clear_cache and count == counts[0],
        )
        print(
            f"  cold={run.cold_compute_ms}ms warm={run.warm_compute_ms}ms "
            f"compact={run.compact_ready_ms}ms masks_cold={run.masks_ms_cold} "
            f"masks_warm={run.masks_ms_warm} errors={run.errors}",
        )
        runs.append(asdict(run))

    report = {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "scenario": {
            "id": scenario.id,
            "name": scenario.name,
            "route_set_id": route_set_id,
            "routes_total": routes_total,
        },
        "profile": args.profile,
        "samples": samples,
        "cache_sizes_mb": _cache_sizes(),
        "runs": runs,
    }

    out = args.output or (
        PROJECT_DIR
        / "reports"
        / f"tariff_rules_benchmark_{datetime.now().strftime('%Y%m%d_%H%M%S')}.json"
    )
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"report: {out}")


if __name__ == "__main__":
    main()
