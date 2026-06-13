from __future__ import annotations

from dataclasses import dataclass

from core.models import MessageType, RailRoad, Shipper, ShipmentType, WagonKind
from scenarios.domain.dto import CreateTariffRuleDTO
from scenarios.domain.services import TariffRuleService
from scenarios.models import Scenario, TariffRule

BENCH_PREFIX = "BENCH-"


@dataclass(frozen=True)
class BenchRulePreset:
    name: str
    parameter: str | None
    operator: str
    values: list | str | int | None
    base_percent: str
    year_values: dict[str, str]


def sample_bench_values() -> dict[str, object]:
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


def build_bench_presets(samples: dict[str, object]) -> list[BenchRulePreset]:
    return [
        BenchRulePreset(
            "wagon_kind",
            "wagon_kind",
            "include",
            [samples["wagon_kind_id"]],
            "100",
            {"2030": "2.0000"},
        ),
        BenchRulePreset(
            "cargo_group",
            "cargo_group",
            "include",
            [samples["cargo_group_code"]],
            "100",
            {"2026": "1.1000"},
        ),
        BenchRulePreset(
            "message_type",
            "message_type",
            "include",
            [samples["message_type_id"]],
            "100",
            {"2027": "1.2000"},
        ),
        BenchRulePreset(
            "shipment_type",
            "shipment_type",
            "include",
            [samples["shipment_type_id"]],
            "50",
            {"2028": "1.3000"},
        ),
        BenchRulePreset(
            "origin_railroad",
            "origin_railroad",
            "include",
            [samples["railroad_code"]],
            "100",
            {"2029": "1.4000"},
        ),
        BenchRulePreset(
            "shipper",
            "shipper",
            "include",
            [samples["shipper_id"]],
            "100",
            {"2031": "1.5000"},
        ),
        BenchRulePreset(
            "holding",
            "shipper_holding",
            "include",
            [samples["holding"]],
            "100",
            {"2032": "1.6000"},
        ),
        BenchRulePreset(
            "distance_lt",
            "distance_belt",
            "lt",
            samples["distance_belt_lt"],
            "100",
            {"2033": "1.7000"},
        ),
        BenchRulePreset(
            "distance_include",
            "distance_belt",
            "include",
            [samples["distance_belt_include"]],
            "100",
            {"2034": "1.8000"},
        ),
        BenchRulePreset("all_routes", None, "include", None, "100", {"2035": "1.9000"}),
    ]


def resolve_bench_scenario(scenario_id: int | None) -> Scenario:
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
        raise ValueError("Сценарии не найдены")
    return scenario


def delete_bench_rules(*, scenario_id: int) -> int:
    qs = TariffRule.objects.filter(scenario_id=scenario_id, name__startswith=BENCH_PREFIX)
    count = qs.count()
    qs.delete()
    return count


def create_bench_rules(
    *,
    scenario: Scenario,
    user,
    presets: list[BenchRulePreset],
    count: int,
) -> list[int]:
    if count < 1 or count > len(presets):
        raise ValueError(f"count должен быть от 1 до {len(presets)}")

    service = TariffRuleService()
    rule_ids: list[int] = []
    for index in range(count):
        preset = presets[index]
        conditions: list[dict] = []
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
            raise RuntimeError(f"create_rule failed for {preset.name}: {errors}")
        rule_ids.append(created.id)
    return rule_ids


def bench_rule_matched_routes(scenario: Scenario) -> list[tuple[str, int]]:
    from calculations.domain.services.route_mask_cache import build_or_load_rule_mask
    from calculations.domain.services.route_mart_store import (
        load_mart_meta,
        load_mart_sidecar_dataframe,
        resolve_mart_parquet_path,
    )
    from calculations.domain.services.scenario_effects_compute import rule_specs_from_context
    from calculations.domain.services.tariff_load import TariffLoadService

    if not scenario.route_set_id:
        return []

    parquet = resolve_mart_parquet_path(route_set_id=scenario.route_set_id)
    if not parquet.is_file():
        return []

    tl = TariffLoadService()
    ctx = tl.build_scenario_context(scenario)
    specs = [
        s for s in rule_specs_from_context(tl, ctx) if s.name.startswith(BENCH_PREFIX)
    ]
    df, _ = load_mart_sidecar_dataframe(parquet, include_charge=True)
    meta = load_mart_meta(parquet)
    return [
        (
            spec.name,
            int(
                build_or_load_rule_mask(
                    route_set_id=scenario.route_set_id,
                    rule_id=spec.id,
                    conditions=spec.conditions,
                    df=df,
                    mart_meta=meta,
                ).sum(),
            ),
        )
        for spec in specs
    ]
