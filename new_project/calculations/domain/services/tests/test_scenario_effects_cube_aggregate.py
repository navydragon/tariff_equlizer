from __future__ import annotations

from decimal import Decimal

import numpy as np
from django.test import TestCase

from calculations.domain.dto.scenario_effects_cube import ScenarioEffectsCubeRequestDTO
from calculations.domain.services.scenario_effects_cache import CompactRouteEffects
from calculations.domain.services.scenario_effects_compact import (
    aggregate_compact_totals_masked,
    aggregate_compact_value,
    aggregate_compact_year_values_masked,
    build_compact_filter_mask,
)
from calculations.domain.services.scenario_effects_cube import (
    ScenarioEffectsCubeService,
    _aggregate_compact_totals,
)


def _normalize_year_buckets(
    buckets: dict[tuple[str, ...], dict[int, Decimal]],
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    quant = Decimal("0.01")
    return {
        key: {
            year: value.quantize(quant)
            for year, value in year_values.items()
        }
        for key, year_values in buckets.items()
    }


def _legacy_aggregate_compact_year_values(
    compact: CompactRouteEffects,
    *,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
    values_by_year: np.ndarray,
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    year_values: dict[tuple[str, ...], dict[int, Decimal]] = {}
    for year_index, year in enumerate(compact.years):
        buckets = aggregate_compact_value(
            compact,
            values=values_by_year[:, year_index],
            group_by=group_by,
            group_by_inner=group_by_inner,
            cargo_groups=cargo_groups,
            holdings=holdings,
        )
        for key, value in buckets.items():
            year_values.setdefault(key, {})[year] = value
    return year_values


def _build_sample_compact(*, n_rules: int = 3) -> CompactRouteEffects:
    n_routes = 12
    years = [2025, 2026, 2027]
    dimensions = {
        "cargo_group": np.array([0, 0, 0, 1, 1, 1, 2, 2, 2, 0, 1, 2], dtype=np.int32),
        "cargo_code": np.zeros(n_routes, dtype=np.int32),
        "direction": np.zeros(n_routes, dtype=np.int32),
        "wagon_kind": np.zeros(n_routes, dtype=np.int32),
        "transport_type": np.zeros(n_routes, dtype=np.int32),
        "shipment_category": np.zeros(n_routes, dtype=np.int32),
        "park_type": np.zeros(n_routes, dtype=np.int32),
        "holding": np.array([0, 0, 1, 1, 0, 1, 0, 1, 0, 1, 0, 1], dtype=np.int32),
    }
    dimension_labels = {
        "cargo_group": ["Уголь", "Руда", "Прочее"],
        "cargo_code": ["C1"],
        "direction": ["D1"],
        "wagon_kind": ["W1"],
        "transport_type": ["T1"],
        "shipment_category": ["S1"],
        "park_type": ["P1"],
        "holding": ["РЖД", "СТ"],
    }
    rng = np.random.default_rng(42)
    base_by_year = rng.random((n_routes, len(years)), dtype=np.float32) * 1000
    rules_by_year = rng.random((n_routes, len(years)), dtype=np.float32) * 500
    charge_by_year = rng.random((n_routes, len(years)), dtype=np.float32) * 2000
    rule_by_year = rng.random((n_rules, n_routes, len(years)), dtype=np.float32) * 100
    rule_meta = [(index + 1, f"Правило {index + 1}") for index in range(n_rules)]
    return CompactRouteEffects(
        years=years,
        dimensions=dimensions,
        dimension_labels=dimension_labels,
        route_ids=np.arange(n_routes, dtype=np.int32),
        baseline_rub=np.ones(n_routes, dtype=np.float32),
        volume_tons=np.ones(n_routes, dtype=np.float32) * 10,
        base_by_year=base_by_year,
        rules_by_year=rules_by_year,
        charge_by_year=charge_by_year,
        rule_meta=rule_meta,
        rule_by_year=rule_by_year,
        volume_by_year=None,
        volume_fallout_by_year=None,
        money_fallout_by_year=None,
    )


class ScenarioEffectsCubeAggregateTests(TestCase):
    def setUp(self) -> None:
        self.compact = _build_sample_compact(n_rules=5)
        self.cargo_groups = ["Уголь", "Руда"]
        self.holdings: list[str] = []

    def test_masked_group_by_matches_legacy_pandas(self) -> None:
        mask = build_compact_filter_mask(
            self.compact,
            cargo_groups=self.cargo_groups,
            holdings=self.holdings,
        )
        for group_by, group_by_inner in (
            ("cargo_group", "none"),
            ("cargo_group", "holding"),
            ("holding", "cargo_group"),
        ):
            with self.subTest(group_by=group_by, group_by_inner=group_by_inner):
                legacy = _legacy_aggregate_compact_year_values(
                    self.compact,
                    group_by=group_by,
                    group_by_inner=group_by_inner,
                    cargo_groups=self.cargo_groups,
                    holdings=self.holdings,
                    values_by_year=self.compact.base_by_year,
                )
                fast = aggregate_compact_year_values_masked(
                    self.compact,
                    mask=mask,
                    values_by_year=self.compact.base_by_year,
                    group_by=group_by,
                    group_by_inner=group_by_inner,
                )
                self.assertEqual(
                    _normalize_year_buckets(legacy),
                    _normalize_year_buckets(fast),
                )

    def test_tariff_decision_totals_match_legacy(self) -> None:
        mask = build_compact_filter_mask(
            self.compact,
            cargo_groups=self.cargo_groups,
            holdings=self.holdings,
        )
        legacy = _aggregate_compact_totals(
            self.compact,
            values_by_year=self.compact.rules_by_year,
            cargo_groups=self.cargo_groups,
            holdings=self.holdings,
        )
        fast = {
            ("ИТОГО",): aggregate_compact_totals_masked(
                self.compact,
                mask=mask,
                values_by_year=self.compact.rules_by_year,
            ),
        }
        self.assertEqual(legacy, fast)

    def test_tariff_decision_rule_batch_matches_per_rule_totals(self) -> None:
        mask = build_compact_filter_mask(
            self.compact,
            cargo_groups=[],
            holdings=[],
        )
        masked_rules = self.compact.rule_by_year[:, mask, :]
        batch = {
            meta_id: masked_rules[index].sum(axis=0)
            for index, (meta_id, _name) in enumerate(self.compact.rule_meta)
        }
        for rule_id, _name in self.compact.rule_meta:
            rule_index = next(
                index
                for index, (meta_id, _label) in enumerate(self.compact.rule_meta)
                if meta_id == rule_id
            )
            legacy = _aggregate_compact_totals(
                self.compact,
                values_by_year=self.compact.rule_by_year[rule_index],
                cargo_groups=[],
                holdings=[],
            )[("ИТОГО",)]
            fast = {
                year: Decimal(str(float(batch[rule_id][index])))
                for index, year in enumerate(self.compact.years)
            }
            self.assertEqual(legacy, fast)

    def test_cube_service_tariff_decision_groups_all_rules(self) -> None:
        service = ScenarioEffectsCubeService()
        from calculations.domain.services.scenario_effects_cache import (
            ScenarioEffectsCachePayload,
        )

        payload = ScenarioEffectsCachePayload(
            user_id=1,
            scenario_id=1,
            years=self.compact.years,
            routes_without_charge=0,
            routes_without_volume=0,
            baseline_total=Decimal("0"),
            compact=self.compact,
        )
        request = ScenarioEffectsCubeRequestDTO(
            cache_key="test",
            group_by="tariff_decision",
            cargo_groups=self.cargo_groups,
        )
        effect_slices = service._build_effect_slices(payload, scenario=type("S", (), {"consider_demand_elasticity": False})())
        grouped = service._aggregate_groups(payload, request, effect_slices)
        self.assertIn("base", grouped)
        self.assertIn("rules_total", grouped)
        self.assertEqual(len([key for key in grouped if key.startswith("rule:")]), 5)
