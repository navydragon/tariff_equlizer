from __future__ import annotations

import time
from decimal import Decimal

import numpy as np
import pandas as pd

from calculations.domain.dto.scenario_effects import ScenarioEffectsComputeResponseDTO
from calculations.domain.services.pandas_tariff_conditions import build_rule_mask
from calculations.domain.services.scenario_effects_cache import (
    CompactRouteEffects,
    ScenarioEffectsCachePayload,
    make_cache_key,
    store_payload,
)
from calculations.domain.services.scenario_effects_compact import (
    build_compact_from_arrays,
)
from calculations.domain.services.scenario_effects_formatting import (
    GlobalTotals,
    build_cards_from_totals,
    format_ths,
)
from calculations.domain.services.route_effects_loader import (
    fetch_route_set_stats,
    fetch_routes_dataframe,
)
from calculations.domain.services.tariff_load import TariffLoadService
from scenarios.models import Scenario


def _effective_rule_coefficient(coefficient: float, base_percent: float) -> float:
    return 1.0 + (coefficient - 1.0) * base_percent / 100.0


def _to_decimal(value: float) -> Decimal:
    return Decimal(str(value))


class ScenarioEffectsPandasService:
    def __init__(self) -> None:
        self._tariff_load = TariffLoadService()

    def compute_pandas(
        self,
        *,
        scenario: Scenario,
        user_id: int,
    ) -> tuple[ScenarioEffectsComputeResponseDTO | None, list[str], dict]:
        started = time.perf_counter()
        context = self._tariff_load.build_scenario_context(scenario)
        t_context = time.perf_counter()
        years = context.years

        df, skipped_charge, skipped_volume = self._load_routes_df(scenario)
        t_load = time.perf_counter()

        compact, global_totals = self._compute_compact(df, context, years)
        t_compute = time.perf_counter()

        filter_options = self._collect_filter_options(df)
        cards = build_cards_from_totals(global_totals, years)
        t_cards = time.perf_counter()

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
                facts=[],
                compact=compact,
            ),
        )
        t_cache = time.perf_counter()

        elapsed_ms = int((t_cache - started) * 1000)
        meta = {
            "engine": "pandas",
            "elapsed_ms": elapsed_ms,
            "timings": {
                "context_ms": int((t_context - started) * 1000),
                "load_ms": int((t_load - t_context) * 1000),
                "compute_ms": int((t_compute - t_load) * 1000),
                "cards_ms": int((t_cards - t_compute) * 1000),
                "cache_ms": int((t_cache - t_cards) * 1000),
            },
        }

        return (
            ScenarioEffectsComputeResponseDTO(
                cache_key=cache_key,
                scenario_id=scenario.id,
                years=years,
                baseline_ths_rub=format_ths(global_totals.baseline_total),
                routes_without_charge=skipped_charge,
                routes_without_volume=skipped_volume,
                cards=cards,
                filter_options=filter_options,
            ),
            [],
            meta,
        )

    def _load_routes_df(
        self,
        scenario: Scenario,
    ) -> tuple[pd.DataFrame, int, int]:
        route_set_id = scenario.route_set_id
        skipped_charge, skipped_volume = fetch_route_set_stats(route_set_id)
        df = fetch_routes_dataframe(route_set_id)
        return df, skipped_charge, skipped_volume

    def _compute_compact(
        self,
        df: pd.DataFrame,
        context,
        years: list[int],
    ) -> tuple[CompactRouteEffects | None, GlobalTotals]:
        if df.empty:
            return None, GlobalTotals()

        n_routes = len(df)
        n_years = len(years)
        initial = df["freight_charge_ths_rub"].astype(float).to_numpy()
        rules_coef = np.ones((n_routes, n_years), dtype=np.float64)
        base_coef_arr = np.array(
            [float(context.base_coef_by_year.get(year, Decimal("1"))) for year in years],
            dtype=np.float64,
        )

        rule_meta: list[tuple[int, str]] = []
        rule_masks: list[np.ndarray] = []
        rule_effective_by_year: list[np.ndarray] = []

        for rule in context.rules:
            mask = build_rule_mask(
                df,
                self._tariff_load._rule_conditions_payload(rule),
            ).to_numpy()
            if not mask.any():
                continue

            year_coefs = {
                value.year: float(value.coefficient)
                for value in rule.year_values.all()
            }
            base_percent = float(rule.base_percent)
            effective_arr = np.array(
                [
                    _effective_rule_coefficient(year_coefs.get(year, 1.0), base_percent)
                    for year in years
                ],
                dtype=np.float64,
            )
            rule_meta.append((rule.id, rule.name))
            rule_masks.append(mask)
            rule_effective_by_year.append(effective_arr)

            for year_index, year in enumerate(years):
                rules_coef[mask, year_index] *= effective_arr[year_index]

        n_rules = len(rule_meta)
        rule_by_year_arr = (
            np.zeros((n_rules, n_routes, n_years), dtype=np.float64)
            if n_rules
            else None
        )

        charge_by_year = np.zeros((n_routes, n_years), dtype=np.float64)
        base_by_year = np.zeros((n_routes, n_years), dtype=np.float64)
        rules_by_year_arr = np.zeros((n_routes, n_years), dtype=np.float64)

        prev = initial.copy()
        for year_index, _year in enumerate(years):
            if year_index == 0:
                charge_by_year[:, year_index] = prev
                continue

            base_coef = base_coef_arr[year_index]
            rules_column = rules_coef[:, year_index]
            current = np.round(prev * (base_coef + rules_column - 1.0), 2)
            base_inc = np.round(prev * (base_coef - 1.0), 2)
            rules_inc = np.round(prev * (rules_column - 1.0), 2)

            if rule_by_year_arr is not None:
                for rule_index, mask in enumerate(rule_masks):
                    effective = rule_effective_by_year[rule_index][year_index]
                    rule_by_year_arr[rule_index, mask, year_index] = np.round(
                        prev[mask] * (effective - 1.0),
                        2,
                    )

            charge_by_year[:, year_index] = current
            base_by_year[:, year_index] = base_inc
            rules_by_year_arr[:, year_index] = rules_inc
            prev = current

        global_totals = GlobalTotals()
        global_totals.baseline_total = sum(_to_decimal(value) for value in initial)
        for year_index, year in enumerate(years):
            global_totals.charge_by_year[year] = _to_decimal(
                float(charge_by_year[:, year_index].sum()),
            )
            if year_index == 0:
                continue
            global_totals.base_by_year[year] = _to_decimal(
                float(base_by_year[:, year_index].sum()),
            )
            global_totals.rules_by_year[year] = _to_decimal(
                float(rules_by_year_arr[:, year_index].sum()),
            )

        compact = build_compact_from_arrays(
            df,
            years=years,
            initial=initial,
            base_by_year=base_by_year,
            rules_by_year_arr=rules_by_year_arr,
            charge_by_year=charge_by_year,
            rule_meta=rule_meta,
            rule_by_year=rule_by_year_arr,
        )
        return compact, global_totals

    @staticmethod
    def _collect_filter_options(df: pd.DataFrame) -> dict[str, list[str]]:
        if df.empty:
            return {"cargo_groups": ["—"], "holdings": ["Прочие"]}

        cargo_groups = set(df["cargo_group"].dropna().astype(str).tolist())
        cargo_groups.add("—")
        holdings = set(df["holding"].dropna().astype(str).tolist())
        return {
            "cargo_groups": sorted(cargo_groups),
            "holdings": sorted(holdings),
        }
