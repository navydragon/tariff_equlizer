import logging
from decimal import Decimal
from unittest import TestCase
from unittest.mock import MagicMock, patch

import numpy as np

from calculations.domain.services.elasticity_fallout_compute import (
    FalloutComputeStats,
    _compute_eligibility_masks,
    compute_fallout_arrays,
    log_fallout_diagnostics,
)
from calculations.domain.services.route_mart_store import MartSidecarView
from calculations.domain.services.scenario_effects_compute import _COMPUTE_DTYPE
from scenarios.models import ElasticityRule
from scenarios.models import Scenario


class FalloutEligibilityMaskTests(TestCase):
    def test_eligibility_masks_count_skips_and_sources(self) -> None:
        skip = np.array([1, 0, 0, 0, 0, 0], dtype=np.uint8)
        source_codes = np.array([0, 0, 1, 2, 3, 0], dtype=np.uint8)
        volumes = np.array([0, 0, 100, 100, 100, 100], dtype=_COMPUTE_DTYPE)
        initial_charge = np.array([0, 0, 0, 50, 50, 50], dtype=_COMPUTE_DTYPE)

        _static_ok, _eligible, stats = _compute_eligibility_masks(
            skip=skip,
            source_codes=source_codes,
            volumes=volumes,
            initial_charge=initial_charge,
            n_routes=6,
        )

        self.assertEqual(stats.routes_total, 6)
        self.assertEqual(stats.skip_elasticity, 1)
        self.assertEqual(stats.skip_no_volume, 1)
        self.assertEqual(stats.skip_no_initial, 1)
        self.assertEqual(stats.skip_source_none, 1)
        self.assertEqual(stats.static_eligible, 3)
        self.assertEqual(stats.dynamic_eligible, 2)
        self.assertEqual(stats.source_direct_model, 0)
        self.assertEqual(stats.source_holding_aggregate, 1)
        self.assertEqual(stats.source_cargo_group_aggregate, 1)


class FalloutDiagnosticsLoggingTests(TestCase):
    def test_log_fallout_diagnostics_emits_summary(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        stats = FalloutComputeStats(
            routes_total=1_000_000,
            dynamic_eligible=250_000,
            loop_routes=250_000,
            routes_computed=200_000,
            skip_elasticity=700_000,
            aggregate_calls=500_000,
            model_row_iters=2_500_000,
        )
        with patch(
            "calculations.domain.services.elasticity_fallout_compute.logger",
            logger,
        ):
            log_fallout_diagnostics(stats)

        message = logger.info.call_args[0][0] % logger.info.call_args[0][1:]
        self.assertIn("Elasticity fallout profile", message)
        self.assertIn("loop_routes=250000", message)
        self.assertIn("eligible=250000", message)
        self.assertIn("aggregate_calls=500000", message)

    def test_to_timings_includes_loop_routes(self) -> None:
        stats = FalloutComputeStats(
            routes_total=1_000_000,
            dynamic_eligible=10_963,
            loop_routes=10_963,
        )
        timings = stats.to_timings()
        self.assertEqual(timings["fallout_loop_routes"], 10_963)
        self.assertEqual(timings["fallout_dynamic_eligible"], 10_963)


class ComputeFalloutArraysDiagnosticsTests(TestCase):
    def test_disabled_elasticity_returns_empty_stats(self) -> None:
        scenario = Scenario(consider_demand_elasticity=False)
        sidecar = MartSidecarView(
            column_arrays={
                "transport_volume_tons": np.array([1.0], dtype=_COMPUTE_DTYPE),
            },
        )
        volume, _money, stats = compute_fallout_arrays(
            sidecar,
            scenario=scenario,
            years=[2025, 2026],
            initial_charge=np.array([100.0], dtype=_COMPUTE_DTYPE),
            charge_by_year=np.array([[100.0, 110.0]], dtype=_COMPUTE_DTYPE),
            turnover_coef=np.array([[1.0, 1.0]], dtype=_COMPUTE_DTYPE),
            model_rows=[],
        )
        self.assertEqual(volume.shape, (1, 2))
        self.assertEqual(stats.routes_total, 1)
        self.assertEqual(stats.dynamic_eligible, 0)


class ComputeFalloutArraysMemoizationTests(TestCase):
    def test_holding_aggregate_retention_is_memoized_by_ratio(self) -> None:
        scenario = Scenario(
            consider_demand_elasticity=True,
            elasticity_set_id=1,
            retention_coefficient_mode="combined",
            consider_enterprise_load=True,
        )

        # Two routes, same group, same ratio -> one retention compute.
        sidecar = MartSidecarView(
            column_arrays={
                "skip_elasticity": np.array([0, 0], dtype=np.uint8),
                "elasticity_source": np.array([2, 2], dtype=np.uint8),  # holding_aggregate
                "transport_volume_tons": np.array(
                    [100.0, 200.0],
                    dtype=_COMPUTE_DTYPE,
                ),
                "message_type_id": np.array([1, 1], dtype=_COMPUTE_DTYPE),
                "cargo_group_id": np.array([10, 10], dtype=_COMPUTE_DTYPE),
                "dim_holding": np.array([1, 1], dtype=_COMPUTE_DTYPE),
                "dim_direction": np.array([1, 1], dtype=_COMPUTE_DTYPE),
            },
        )

        years = [2025, 2026]
        initial_charge = np.array([100.0, 100.0], dtype=_COMPUTE_DTYPE)
        charge_by_year = np.array(
            [[100.0, 110.0], [100.0, 110.0]],
            dtype=_COMPUTE_DTYPE,
        )
        turnover_coef = np.array([[1.0, 1.0], [1.0, 1.0]], dtype=_COMPUTE_DTYPE)

        rule = ElasticityRule(
            id=1,
            elasticity_set_id=1,
            cargo_group_id=10,
            cargo_id=None,
            message_type_id=None,
            position=1,
        )
        point = type(
            "Point",
            (),
            {"marginality": Decimal("0.05"), "coefficient": Decimal("0.95")},
        )()

        class _RuleRepo:
            def list_by_set(self, _set_id):
                return [rule]

        class _PointRepo:
            def list_by_rules(self, _rule_ids):
                return {1: [point]}

        # One model-row group keyed by holding/direction/message_type/cargo_group.
        model_row = type(
            "Row",
            (),
            {
                "cargo_group_id": 10,
                "cargo_id": 101,
                "message_type_id": 1,
                "market_price_per_ton": Decimal("5000"),
                "production_cost_per_ton": Decimal("3000"),
                "total_cost_per_ton": Decimal("0"),
                "rzd_cost_total_per_ton": Decimal("800"),
                "operators_cost_per_ton": Decimal("100"),
                "transshipment_cost_per_ton": Decimal("50"),
                "enterprise_load_coefficient": Decimal("1"),
                "fixed_retention_coefficient": Decimal("0"),
                "transport_volume_tons": Decimal("1000"),
            },
        )()

        def _fake_build_model_route_group_indexes(_rows):
            holding_key = ("H1", "D1", 1, 10)
            return {holding_key: [model_row]}, {}

        retention_calls = {"n": 0}

        def _fake_weighted_retention_numpy(*_args, **_kwargs):
            retention_calls["n"] += 1
            return 1.05

        with patch(
            "calculations.domain.services.elasticity_fallout_compute.ElasticityRuleRepository",
            new=lambda: _RuleRepo(),
        ), patch(
            "calculations.domain.services.elasticity_fallout_compute.ElasticityRulePointRepository",
            new=lambda: _PointRepo(),
        ), patch(
            "calculations.domain.services.elasticity_fallout_compute.build_model_route_group_indexes",
            new=_fake_build_model_route_group_indexes,
        ), patch(
            "calculations.domain.services.elasticity_fallout_compute._weighted_retention_numpy",
            new=_fake_weighted_retention_numpy,
        ):
            _volume, _money, stats = compute_fallout_arrays(
                sidecar,
                scenario=scenario,
                years=years,
                initial_charge=initial_charge,
                charge_by_year=charge_by_year,
                turnover_coef=turnover_coef,
                model_rows=[model_row],
                dimension_labels={
                    "holding": ["—", "H1"],
                    "direction": ["—", "D1"],
                },
            )

        self.assertEqual(retention_calls["n"], 1)
        self.assertEqual(stats.aggregate_calls, 1)
        self.assertEqual(stats.aggregate_cache_misses, 1)
