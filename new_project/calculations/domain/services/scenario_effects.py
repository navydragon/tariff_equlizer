from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import QuerySet

from calculations.domain.dto.scenario_effects import (
    EffectChartDTO,
    EffectTableRowDTO,
    ScenarioEffectsAggregateRequestDTO,
    ScenarioEffectsAggregateResponseDTO,
    ScenarioEffectsComputeResponseDTO,
    ScenarioEffectsRequestDTO,
    ScenarioEffectsResponseDTO,
)
from calculations.domain.services.grouping import build_group_keys
from calculations.domain.services.scenario_effects_compact import aggregate_compact_buckets
from calculations.domain.services.scenario_effects_cache import (
    COMPACT_API_WAIT_TIMEOUT_SECONDS,
    RouteEffectFact,
    ScenarioEffectsCachePayload,
    get_payload,
    get_payload_ready,
    make_cache_key,
    store_payload,
    validate_cache_access,
)
from calculations.domain.services.scenario_effects_formatting import (
    GlobalTotals as _GlobalTotals,
    build_cards_from_totals,
    format_bln as _format_bln,
    format_rub as _format_rub,
    pct as _pct,
)
from calculations.domain.services.tariff_load import TariffLoadService
from core.models import Route
from scenarios.models import Scenario


@dataclass
class _AggBucket:
    base: Decimal = Decimal("0")
    rules: Decimal = Decimal("0")
    prev_charge: Decimal = Decimal("0")

    @property
    def total(self) -> Decimal:
        return self.base + self.rules


class ScenarioEffectsService:
    def __init__(self) -> None:
        self._tariff_load = TariffLoadService()

    def compute(
        self,
        *,
        scenario: Scenario,
        user_id: int,
    ) -> tuple[ScenarioEffectsComputeResponseDTO | None, list[str]]:
        context = self._tariff_load.build_scenario_context(scenario)
        years = context.years

        facts, skipped_charge, skipped_volume, global_totals = self._compute_route_facts(
            scenario,
            context,
        )
        filter_options = self._collect_filter_options_from_db(scenario)
        cards = build_cards_from_totals(global_totals, years)

        cache_key = make_cache_key(user_id=user_id, scenario_id=scenario.id)
        store_payload(
            cache_key=cache_key,
            payload=ScenarioEffectsCachePayload(
                user_id=user_id,
                scenario_id=scenario.id,
                years=years,
                routes_without_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                baseline_total=global_totals.baseline_total,
                facts=facts,
            ),
        )

        return (
            ScenarioEffectsComputeResponseDTO(
                cache_key=cache_key,
                scenario_id=scenario.id,
                years=years,
                baseline_rub=_format_rub(global_totals.baseline_total),
                routes_without_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                cards=cards,
                filter_options=filter_options,
            ),
            [],
        )

    def aggregate(
        self,
        *,
        scenario: Scenario,
        user_id: int,
        request: ScenarioEffectsAggregateRequestDTO,
    ) -> tuple[ScenarioEffectsAggregateResponseDTO | None, list[str]]:
        payload = get_payload_ready(
            request.cache_key,
            timeout_seconds=COMPACT_API_WAIT_TIMEOUT_SECONDS,
        )
        if payload is None:
            return None, ["Расчёт устарел. Выберите сценарий заново."]

        access_errors = validate_cache_access(
            payload=payload,
            user_id=user_id,
            scenario_id=scenario.id,
        )
        if access_errors:
            return None, access_errors

        if payload.compact is None and payload.compact_pending:
            return None, ["Расчёт ещё выполняется. Повторите запрос через несколько секунд."]

        if payload.compact is None and not payload.facts:
            return None, ["Расчёт устарел. Выберите сценарий заново."]

        years = payload.years
        if request.year not in years:
            return None, [f"Год {request.year} вне диапазона сценария"]
        if request.year == years[0]:
            return None, ["Для первого года сценария эффект равен нулю"]

        prev_year = years[years.index(request.year) - 1]
        buckets = self._aggregate_facts(
            payload.facts,
            year=request.year,
            prev_year=prev_year,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
            cargo_groups=request.cargo_groups,
            holdings=request.holdings,
            compact=payload.compact,
        )

        if request.group_by_inner == "none":
            grand = _AggBucket(
                base=sum(
                    (b.base for key, b in buckets.items() if len(key) == 1),
                    Decimal("0"),
                ),
                rules=sum(
                    (b.rules for key, b in buckets.items() if len(key) == 1),
                    Decimal("0"),
                ),
                prev_charge=sum(
                    (b.prev_charge for key, b in buckets.items() if len(key) == 1),
                    Decimal("0"),
                ),
            )
        else:
            grand = _AggBucket(
                base=sum(
                    (
                        b.base
                        for key, b in buckets.items()
                        if len(key) == 2 and key[1] == "ИТОГО"
                    ),
                    Decimal("0"),
                ),
                rules=sum(
                    (
                        b.rules
                        for key, b in buckets.items()
                        if len(key) == 2 and key[1] == "ИТОГО"
                    ),
                    Decimal("0"),
                ),
                prev_charge=sum(
                    (
                        b.prev_charge
                        for key, b in buckets.items()
                        if len(key) == 2 and key[1] == "ИТОГО"
                    ),
                    Decimal("0"),
                ),
            )

        table_rows = self._format_table_rows(
            buckets,
            grand,
            group_by_inner=request.group_by_inner,
        )
        chart = self._build_chart(buckets, group_by_inner=request.group_by_inner)

        return (
            ScenarioEffectsAggregateResponseDTO(
                table_rows=table_rows,
                chart=chart,
            ),
            [],
        )

    def calculate(
        self,
        *,
        scenario: Scenario,
        request: ScenarioEffectsRequestDTO,
        user_id: int,
    ) -> tuple[ScenarioEffectsResponseDTO | None, list[str]]:
        """Полный расчёт за один вызов (для тестов и обратной совместимости)."""
        compute_result, compute_errors = self.compute(
            scenario=scenario,
            user_id=user_id,
        )
        if compute_errors or compute_result is None:
            return None, compute_errors

        aggregate_request = ScenarioEffectsAggregateRequestDTO(
            cache_key=compute_result.cache_key,
            year=request.year,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
            cargo_groups=request.cargo_groups,
            holdings=request.holdings,
        )
        aggregate_result, aggregate_errors = self.aggregate(
            scenario=scenario,
            user_id=user_id,
            request=aggregate_request,
        )
        if aggregate_errors or aggregate_result is None:
            return None, aggregate_errors

        return (
            ScenarioEffectsResponseDTO(
                scenario_id=compute_result.scenario_id,
                years=compute_result.years,
                baseline_rub=compute_result.baseline_rub,
                routes_without_charge=compute_result.routes_without_charge,
                cards=compute_result.cards,
                filter_options=compute_result.filter_options,
                table_rows=aggregate_result.table_rows,
                chart=aggregate_result.chart,
            ),
            [],
        )

    def _compute_route_facts(
        self,
        scenario: Scenario,
        context,
    ) -> tuple[list[RouteEffectFact], int, int, _GlobalTotals]:
        all_routes_qs: QuerySet[Route] = Route.objects.filter(
            route_set_id=scenario.route_set_id,
        )
        routes_qs = all_routes_qs.filter(
            freight_charge_rub__gt=0,
        ).select_related(
            "cargo__cargo_group",
            "shipper",
            "message_type",
            "wagon_kind",
            "shipment_type",
            "origin_station__railroad",
        )

        skipped_charge = all_routes_qs.count() - routes_qs.count()
        skipped_volume = all_routes_qs.exclude(
            transport_volume_tons__gt=0,
        ).count()
        rule_match_sets = self._tariff_load.build_rule_match_sets(
            routes_qs,
            context.rules,
        )

        facts: list[RouteEffectFact] = []
        global_totals = _GlobalTotals()
        years = context.years

        for route in routes_qs.iterator(chunk_size=2000):
            effects = self._tariff_load.compute_freight_charge_effects(
                route,
                context,
                rule_match_sets,
            )
            if effects is None:
                skipped_charge += 1
                continue

            dimensions = _route_dimensions(route)
            baseline = route.freight_charge_rub or Decimal("0")
            volume = route.transport_volume_tons or Decimal("0")

            global_totals.baseline_total += baseline
            for year in years:
                global_totals.charge_by_year[year] += effects.charge_by_year.get(
                    year,
                    Decimal("0"),
                )
            for index, year in enumerate(years):
                if index == 0:
                    continue
                global_totals.base_by_year[year] += effects.base_by_year.get(
                    year,
                    Decimal("0"),
                )
                global_totals.rules_by_year[year] += effects.rules_by_year.get(
                    year,
                    Decimal("0"),
                )

            facts.append(
                RouteEffectFact(
                    cargo_group=dimensions.cargo_group,
                    cargo_code=dimensions.cargo_code,
                    direction=dimensions.direction,
                    wagon_kind=dimensions.wagon_kind,
                    transport_type=dimensions.transport_type,
                    shipment_category=dimensions.shipment_category,
                    park_type=dimensions.park_type,
                    holding=dimensions.holding,
                    baseline_rub=baseline,
                    volume_tons=volume,
                    base_by_year=dict(effects.base_by_year),
                    rules_by_year=dict(effects.rules_by_year),
                    charge_by_year=dict(effects.charge_by_year),
                    rule_by_year={
                        rule_id: dict(year_values)
                        for rule_id, year_values in effects.rule_by_year.items()
                    },
                ),
            )

        return facts, skipped_charge, skipped_volume, global_totals

    def _aggregate_facts(
        self,
        facts: list[RouteEffectFact],
        *,
        year: int,
        prev_year: int,
        group_by: str,
        group_by_inner: str,
        cargo_groups: list[str],
        holdings: list[str],
        compact=None,
    ) -> dict[tuple[str, ...], _AggBucket]:
        if compact is not None:
            raw_buckets = aggregate_compact_buckets(
                compact,
                year=year,
                prev_year=prev_year,
                group_by=group_by,
                group_by_inner=group_by_inner,
                cargo_groups=cargo_groups,
                holdings=holdings,
            )
            return {
                key: _AggBucket(base=base, rules=rules, prev_charge=prev_charge)
                for key, (base, rules, prev_charge) in raw_buckets.items()
            }

        cargo_filter = set(cargo_groups) if cargo_groups else None
        holding_filter = set(holdings) if holdings else None
        buckets: dict[tuple[str, ...], _AggBucket] = defaultdict(_AggBucket)

        for fact in facts:
            if cargo_filter is not None and fact.cargo_group not in cargo_filter:
                continue
            if holding_filter is not None and fact.holding not in holding_filter:
                continue

            base_inc = fact.base_by_year.get(year, Decimal("0"))
            rules_inc = fact.rules_by_year.get(year, Decimal("0"))
            prev_charge = fact.charge_by_year.get(prev_year, Decimal("0"))

            for key in build_group_keys(
                fact,
                group_by=group_by,
                group_by_inner=group_by_inner,
            ):
                bucket = buckets[key]
                bucket.base += base_inc
                bucket.rules += rules_inc
                bucket.prev_charge += prev_charge

        return buckets

    @staticmethod
    def _collect_filter_options_from_db(scenario: Scenario) -> dict[str, list[str]]:
        qs = Route.objects.filter(
            route_set_id=scenario.route_set_id,
            freight_charge_rub__gt=0,
        )

        cargo_groups = {
            name
            for name in qs.filter(cargo__cargo_group__name__isnull=False)
            .values_list("cargo__cargo_group__name", flat=True)
            .distinct()
            if name
        }
        cargo_groups.add("—")

        holdings = {
            (value or "").strip() or "Прочие"
            for value in qs.filter(shipper__isnull=False)
            .values_list("shipper__holding", flat=True)
            .distinct()
        }

        return {
            "cargo_groups": sorted(cargo_groups),
            "holdings": sorted(holdings),
        }

    def _format_table_rows(
        self,
        buckets: dict[tuple[str, ...], _AggBucket],
        grand: _AggBucket,
        *,
        group_by_inner: str,
    ) -> list[EffectTableRowDTO]:
        rows: list[EffectTableRowDTO] = []

        rows.append(_bucket_to_row("ИТОГО", grand, is_subtotal=True))

        if group_by_inner == "none":
            keys = sorted(
                (key for key in buckets if len(key) == 1),
                key=lambda k: buckets[k].total,
                reverse=True,
            )
            for key in keys:
                rows.append(
                    _bucket_to_row(key[0], buckets[key], is_subtotal=False),
                )
            return rows

        outers = sorted({key[0] for key in buckets if len(key) == 2})
        for outer in outers:
            subtotal_key = (outer, "ИТОГО")
            if subtotal_key in buckets:
                rows.append(
                    _bucket_to_row(outer, buckets[subtotal_key], is_subtotal=True),
                )

            inner_keys = sorted(
                (
                    key
                    for key in buckets
                    if len(key) == 2 and key[0] == outer and key[1] != "ИТОГО"
                ),
                key=lambda k: buckets[k].total,
                reverse=True,
            )
            for key in inner_keys:
                rows.append(
                    _bucket_to_row(
                        f"  {key[1]}",
                        buckets[key],
                        is_subtotal=False,
                    ),
                )

        return rows

    def _build_chart(
        self,
        buckets: dict[tuple[str, ...], _AggBucket],
        *,
        group_by_inner: str,
    ) -> EffectChartDTO:
        if group_by_inner == "none":
            candidates = [
                (key[0], buckets[key])
                for key in buckets
                if len(key) == 1
            ]
        else:
            candidates = [
                (key[0], buckets[key])
                for key in buckets
                if len(key) == 2 and key[1] == "ИТОГО"
            ]

        candidates.sort(key=lambda item: item[1].total)
        top = candidates[-10:]

        return EffectChartDTO(
            labels=[label for label, _ in top],
            base_bln=[_format_bln(bucket.base) for _, bucket in top],
            rules_bln=[_format_bln(bucket.rules) for _, bucket in top],
        )


@dataclass(frozen=True)
class _RouteDimensions:
    cargo_group: str
    cargo_code: str
    direction: str
    wagon_kind: str
    transport_type: str
    shipment_category: str
    park_type: str
    holding: str


def _route_dimensions(route: Route) -> _RouteDimensions:
    if route.cargo_id and route.cargo.cargo_group_id:
        cargo_group = route.cargo.cargo_group.name
    else:
        cargo_group = "—"

    if route.cargo_id:
        cargo_code = str(route.cargo.code)
    else:
        cargo_code = "—"

    direction = "—"
    if route.origin_station_id:
        railroad = getattr(route.origin_station, "railroad", None)
        if railroad is not None:
            direction = (getattr(railroad, "direction", "") or "").strip() or "—"

    if route.wagon_kind_id:
        wagon_kind = route.wagon_kind.name
    else:
        wagon_kind = "—"

    if route.message_type_id:
        transport_type = route.message_type.name
    else:
        transport_type = "—"

    shipment_category = (route.shipment_category or "").strip() or "—"
    park_type = (route.park_type or "").strip() or "—"

    holding = "Прочие"
    if route.shipper_id:
        holding = (route.shipper.holding or "").strip() or "Прочие"

    return _RouteDimensions(
        cargo_group=cargo_group,
        cargo_code=cargo_code,
        direction=direction,
        wagon_kind=wagon_kind,
        transport_type=transport_type,
        shipment_category=shipment_category,
        park_type=park_type,
        holding=holding,
    )


def _bucket_to_row(
    label: str,
    bucket: _AggBucket,
    *,
    is_subtotal: bool,
) -> EffectTableRowDTO:
    prev = bucket.prev_charge if bucket.prev_charge > 0 else Decimal("1")
    return EffectTableRowDTO(
        label=label,
        is_subtotal=is_subtotal,
        base_rub=_format_rub(bucket.base),
        base_pct=_pct(bucket.base, prev),
        rules_rub=_format_rub(bucket.rules),
        rules_pct=_pct(bucket.rules, prev),
        total_rub=_format_rub(bucket.total),
        total_pct=_pct(bucket.total, prev),
    )
