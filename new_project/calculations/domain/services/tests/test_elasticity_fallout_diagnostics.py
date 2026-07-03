import logging
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
            column_arrays={"transport_volume_tons": np.array([1.0], dtype=_COMPUTE_DTYPE)},
        )
        volume, money, stats = compute_fallout_arrays(
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
