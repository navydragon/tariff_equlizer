from __future__ import annotations

import time
from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP
from typing import Any, Callable

import numpy as np

from calculations.domain.constants import GROUP_BY_LABELS
from calculations.domain.dto.scenario_effects_cube import (
    CubeTableRowDTO,
    ScenarioEffectsCubeRequestDTO,
    ScenarioEffectsCubeResponseDTO,
)
from calculations.domain.services.grouping import aggregate_by_groups, build_group_keys
from calculations.domain.services.scenario_effects_compact import (
    aggregate_compact_totals_masked,
    aggregate_compact_year_values_masked,
    build_compact_filter_mask,
)
from calculations.domain.services.scenario_effects_cache import (
    COMPACT_API_WAIT_TIMEOUT_SECONDS,
    CompactRouteEffects,
    RouteEffectFact,
    ScenarioEffectsCachePayload,
    get_payload_ready,
    validate_cache_access,
)
from calculations.domain.units import RUB_PER_BLN
from core.domain.cargo.ordering import group_key_sort_key
from scenarios.models import Scenario, TariffRule

_BLN_QUANT = Decimal("0.001")

_EFFECT_BASE = "Базовая индексация"
_EFFECT_RULES_TOTAL = "Отдельные тарифные решения"
_EFFECT_VOLUME_FALLOUT = "Выпадение объёмов (млн т)"
_EFFECT_MONEY_FALLOUT = "Выпадение доходов"

# Cube HTML/JSON is not cached: each cube API call re-aggregates compact arrays.
# L2 disk (scenario_compute) and L3 session cache_key hold KPI, compact, rule_by_year.


def _format_mln_tons(value: Decimal) -> str:
    mln = (value / Decimal("1000000")).quantize(_BLN_QUANT, rounding=ROUND_HALF_UP)
    return format(mln, "f")


def _format_bln(value: Decimal) -> str:
    bln = (value / RUB_PER_BLN).quantize(_BLN_QUANT, rounding=ROUND_HALF_UP)
    return format(bln, "f")


def _total_label(years: list[int]) -> str:
    if not years:
        return "Итого"
    return f"{years[0]}–{years[-1]}"


def _payload_has_effects_data(payload: ScenarioEffectsCachePayload) -> bool:
    """Достаточно compact/facts для базовой и суммарной разбивки по эффектам."""
    if payload.compact is not None:
        return True
    return bool(payload.facts)


def _aggregate_compact_totals(
    compact: CompactRouteEffects,
    *,
    values_by_year: np.ndarray,
    cargo_groups: list[str],
    holdings: list[str],
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    mask = build_compact_filter_mask(
        compact,
        cargo_groups=cargo_groups,
        holdings=holdings,
    )
    year_values = aggregate_compact_totals_masked(
        compact,
        mask=mask,
        values_by_year=values_by_year,
    )
    return {("ИТОГО",): year_values}


def _aggregate_facts_totals(
    facts: list[RouteEffectFact],
    *,
    value_fn,
    cargo_groups: list[str],
    holdings: list[str],
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    cargo_filter = set(cargo_groups) if cargo_groups else None
    holding_filter = set(holdings) if holdings else None
    year_values: dict[int, Decimal] = defaultdict(Decimal)

    for fact in facts:
        if cargo_filter is not None and fact.cargo_group not in cargo_filter:
            continue
        if holding_filter is not None and fact.holding not in holding_filter:
            continue
        for year, value in value_fn(fact).items():
            year_values[year] += value

    return {("ИТОГО",): dict(year_values)}


class ScenarioEffectsCubeService:
    def aggregate(
        self,
        *,
        scenario: Scenario,
        user_id: int,
        request: ScenarioEffectsCubeRequestDTO,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> tuple[ScenarioEffectsCubeResponseDTO | None, list[str], dict[str, Any]]:
        started = time.perf_counter()
        timings: dict[str, int] = {}

        t_payload = time.perf_counter()
        payload = get_payload_ready(
            request.cache_key,
            timeout_seconds=COMPACT_API_WAIT_TIMEOUT_SECONDS,
        )
        timings["payload_ready_ms"] = int((time.perf_counter() - t_payload) * 1000)
        if payload is None:
            return None, ["Кэш расчёта устарел или недоступен. Выполните пересчёт."], {}

        access_errors = validate_cache_access(
            payload=payload,
            user_id=user_id,
            scenario_id=scenario.id,
        )
        if access_errors:
            return None, access_errors, {}

        if payload.compact is None:
            return None, ["Расчёт ещё выполняется. Повторите запрос через несколько секунд."], {}

        if (
            request.group_by == "tariff_decision"
            or request.group_by_inner == "tariff_decision"
        ) and payload.compact.rule_by_year is None:
            if payload.compact.rule_meta:
                return None, [
                    "Расчёт ещё выполняется. Повторите запрос через несколько секунд.",
                ], {}

        if not _payload_has_effects_data(payload):
            return None, [
                "Кэш расчёта устарел или недоступен. Выполните пересчёт.",
            ], {}

        if on_progress:
            on_progress(8, "Подготовка срезов эффектов…")

        t_slices = time.perf_counter()
        effect_slices = self._build_effect_slices(payload, scenario=scenario)
        timings["effect_slices_ms"] = int((time.perf_counter() - t_slices) * 1000)

        if on_progress:
            on_progress(12, "Агрегация по группам…")

        t_groups = time.perf_counter()
        group_buckets = self._aggregate_groups(
            payload,
            request,
            effect_slices,
            on_progress=on_progress,
        )
        timings["aggregate_groups_ms"] = int((time.perf_counter() - t_groups) * 1000)

        if on_progress:
            on_progress(92, "Формирование таблицы…")

        t_rows = time.perf_counter()
        rows = self._build_rows(
            group_buckets=group_buckets,
            effect_slices=effect_slices,
            years=payload.years,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
        )
        timings["build_rows_ms"] = int((time.perf_counter() - t_rows) * 1000)

        if on_progress:
            on_progress(99, "Завершение…")

        group_by_label = GROUP_BY_LABELS.get(request.group_by, request.group_by)
        group_by_inner_label = (
            GROUP_BY_LABELS.get(request.group_by_inner)
            if request.group_by_inner != "none"
            else None
        )

        elapsed_ms = int((time.perf_counter() - started) * 1000)
        meta = {"elapsed_ms": elapsed_ms, "timings": timings}
        return (
            ScenarioEffectsCubeResponseDTO(
                years=payload.years,
                total_column_label=_total_label(payload.years),
                unit="млрд руб.",
                group_by_label=group_by_label,
                group_by_inner_label=group_by_inner_label,
                rows=rows,
            ),
            [],
            meta,
        )

    def _build_effect_slices(
        self,
        payload: ScenarioEffectsCachePayload,
        *,
        scenario: Scenario,
    ) -> list[tuple[str, str | None]]:
        slices: list[tuple[str, str | None]] = [
            ("base", _EFFECT_BASE),
            ("rules_total", _EFFECT_RULES_TOTAL),
        ]

        if payload.compact is not None:
            if payload.compact.rule_by_year is not None:
                for rule_id, rule_name in payload.compact.rule_meta:
                    slices.append((f"rule:{rule_id}", rule_name))
            if (
                scenario.consider_demand_elasticity
            ):
                slices.append(("volume_fallout", _EFFECT_VOLUME_FALLOUT))
                slices.append(("money_fallout", _EFFECT_MONEY_FALLOUT))
        else:
            rules = TariffRule.objects.filter(
                scenario_id=scenario.id,
                is_enabled=True,
            ).order_by(
                "position",
                "id",
            )
            for rule in rules:
                if any(rule.id in fact.rule_by_year for fact in payload.facts):
                    slices.append((f"rule:{rule.id}", rule.name))

        return slices

    def _aggregate_groups(
        self,
        payload: ScenarioEffectsCachePayload,
        request: ScenarioEffectsCubeRequestDTO,
        effect_slices: list[tuple[str, str | None]],
        *,
        on_progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, dict[tuple[str, ...], dict[int, Decimal]]]:
        if payload.compact is None:
            return self._aggregate_groups_from_facts(payload, request, effect_slices)

        compact = payload.compact
        mask = build_compact_filter_mask(
            compact,
            cargo_groups=request.cargo_groups,
            holdings=request.holdings,
        )
        rule_index_by_id = {
            meta_id: index
            for index, (meta_id, _name) in enumerate(compact.rule_meta)
        }
        value_matrices = {
            effect_key: self._compact_values_matrix(
                compact,
                effect_key=effect_key,
                rule_index_by_id=rule_index_by_id,
            )
            for effect_key, _label in effect_slices
        }

        if request.group_by == "tariff_decision":
            return self._aggregate_groups_tariff_decision(
                compact=compact,
                mask=mask,
                effect_slices=effect_slices,
                value_matrices=value_matrices,
                on_progress=on_progress,
            )

        result: dict[str, dict[tuple[str, ...], dict[int, Decimal]]] = {}
        total = len(effect_slices)
        for index, (effect_key, label) in enumerate(effect_slices):
            result[effect_key] = aggregate_compact_year_values_masked(
                compact,
                mask=mask,
                values_by_year=value_matrices[effect_key],
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
            )
            if on_progress and total:
                pct = 12 + int(78 * (index + 1) / total)
                slice_label = label or effect_key
                on_progress(
                    pct,
                    f"Агрегация: {slice_label} ({index + 1}/{total})",
                )
        return result

    def _aggregate_groups_tariff_decision(
        self,
        *,
        compact: CompactRouteEffects,
        mask: np.ndarray,
        effect_slices: list[tuple[str, str | None]],
        value_matrices: dict[str, np.ndarray],
        on_progress: Callable[[int, str], None] | None = None,
    ) -> dict[str, dict[tuple[str, ...], dict[int, Decimal]]]:
        totals_key = ("ИТОГО",)
        result: dict[str, dict[tuple[str, ...], dict[int, Decimal]]] = {}
        rule_sums_by_id: dict[int, np.ndarray] | None = None
        if compact.rule_by_year is not None:
            if on_progress:
                on_progress(20, "Суммирование по тарифным решениям…")
            masked_rules = compact.rule_by_year[:, mask, :]
            rule_sums_by_id = {
                meta_id: masked_rules[index].sum(axis=0)
                for index, (meta_id, _name) in enumerate(compact.rule_meta)
            }

        total = len(effect_slices)
        for slice_index, (effect_key, label) in enumerate(effect_slices):
            if effect_key.startswith("rule:") and rule_sums_by_id is not None:
                rule_id = int(effect_key.split(":", 1)[1])
                sums = rule_sums_by_id.get(rule_id)
                if sums is None:
                    result[effect_key] = {}
                else:
                    year_values = {
                        year: Decimal(str(float(sums[year_index])))
                        for year_index, year in enumerate(compact.years)
                    }
                    result[effect_key] = {totals_key: year_values}
            else:
                year_values = aggregate_compact_totals_masked(
                    compact,
                    mask=mask,
                    values_by_year=value_matrices[effect_key],
                )
                result[effect_key] = {totals_key: year_values}

            if on_progress and total:
                pct = 20 + int(70 * (slice_index + 1) / total)
                slice_label = label or effect_key
                on_progress(
                    pct,
                    f"Тарифные решения: {slice_label} ({slice_index + 1}/{total})",
                )
        return result

    def _aggregate_groups_from_facts(
        self,
        payload: ScenarioEffectsCachePayload,
        request: ScenarioEffectsCubeRequestDTO,
        effect_slices: list[tuple[str, str | None]],
    ) -> dict[str, dict[tuple[str, ...], dict[int, Decimal]]]:
        result: dict[str, dict[tuple[str, ...], dict[int, Decimal]]] = {}
        for effect_key, _label in effect_slices:
            value_fn = self._facts_value_fn(payload.facts, effect_key=effect_key)
            if request.group_by == "tariff_decision":
                buckets = _aggregate_facts_totals(
                    payload.facts,
                    value_fn=value_fn,
                    cargo_groups=request.cargo_groups,
                    holdings=request.holdings,
                )
            else:
                buckets = self._aggregate_facts_by_year(
                    payload.facts,
                    request=request,
                    value_fn=value_fn,
                )
            result[effect_key] = buckets
        return result

    @staticmethod
    def _compact_values_matrix(
        compact: CompactRouteEffects,
        *,
        effect_key: str,
        rule_index_by_id: dict[int, int] | None = None,
    ) -> np.ndarray:
        if effect_key == "base":
            return compact.base_by_year
        if effect_key == "rules_total":
            return compact.rules_by_year
        if effect_key == "volume_fallout":
            if compact.volume_fallout_by_year is None:
                return np.zeros_like(compact.base_by_year)
            return compact.volume_fallout_by_year
        if effect_key == "money_fallout":
            if compact.money_fallout_by_year is None:
                return np.zeros_like(compact.base_by_year)
            return compact.money_fallout_by_year

        rule_id = int(effect_key.split(":", 1)[1])
        if rule_index_by_id is not None:
            rule_index = rule_index_by_id.get(rule_id)
        else:
            rule_index = next(
                (
                    index
                    for index, (meta_id, _name) in enumerate(compact.rule_meta)
                    if meta_id == rule_id
                ),
                None,
            )
        if rule_index is None:
            raise ValueError(f"rule_id {rule_id} missing in compact payload")
        if compact.rule_by_year is None:
            raise ValueError("rule_by_year missing in compact payload")
        return compact.rule_by_year[rule_index]

    @staticmethod
    def _facts_value_fn(
        facts: list[RouteEffectFact],
        *,
        effect_key: str,
    ):
        if effect_key == "base":
            return lambda fact: fact.base_by_year
        if effect_key == "rules_total":
            return lambda fact: fact.rules_by_year

        rule_id = int(effect_key.split(":", 1)[1])
        return lambda fact: fact.rule_by_year.get(rule_id, {})

    def _aggregate_facts_by_year(
        self,
        facts: list[RouteEffectFact],
        *,
        request: ScenarioEffectsCubeRequestDTO,
        value_fn,
    ) -> dict[tuple[str, ...], dict[int, Decimal]]:
        cargo_filter = set(request.cargo_groups) if request.cargo_groups else None
        holding_filter = set(request.holdings) if request.holdings else None
        buckets: dict[tuple[str, ...], dict[int, Decimal]] = {}

        for fact in facts:
            if cargo_filter is not None and fact.cargo_group not in cargo_filter:
                continue
            if holding_filter is not None and fact.holding not in holding_filter:
                continue

            year_values = value_fn(fact)
            for key in build_group_keys(
                fact,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
            ):
                bucket = buckets.setdefault(key, defaultdict(Decimal))
                for year, value in year_values.items():
                    bucket[year] += value

        return {
            key: dict(year_values) for key, year_values in buckets.items()
        }

    @staticmethod
    def _build_rows(
        *,
        group_buckets: dict[str, dict[tuple[str, ...], dict[int, Decimal]]],
        effect_slices: list[tuple[str, str | None]],
        years: list[int],
        group_by: str,
        group_by_inner: str,
    ) -> list[CubeTableRowDTO]:
        if not effect_slices:
            return []

        reference_key = effect_slices[0][0]
        group_keys = sorted(
            group_buckets.get(reference_key, {}).keys(),
            key=lambda key: group_key_sort_key(
                key,
                group_by=group_by,
                group_by_inner=group_by_inner,
            ),
        )

        rows: list[CubeTableRowDTO] = []
        for group_key in group_keys:
            if group_by_inner != "none" and len(group_key) > 1 and group_key[1] == "ИТОГО":
                continue

            group_label = group_key[0]
            group_inner_label = group_key[1] if len(group_key) > 1 else None
            if group_by == "tariff_decision":
                group_label = "ИТОГО"
                group_inner_label = None

            for effect_key, effect_label in effect_slices:
                year_values = group_buckets.get(effect_key, {}).get(group_key, {})
                formatter = (
                    _format_mln_tons
                    if effect_key == "volume_fallout"
                    else _format_bln
                )
                formatted_years = {
                    year: formatter(year_values.get(year, Decimal("0")))
                    for year in years
                }
                total = sum(
                    (year_values.get(year, Decimal("0")) for year in years),
                    Decimal("0"),
                )
                rows.append(
                    CubeTableRowDTO(
                        group_label=group_label,
                        group_inner_label=group_inner_label,
                        effect_label=effect_label or effect_key,
                        years=formatted_years,
                        total=formatter(total),
                    ),
                )

        return rows
