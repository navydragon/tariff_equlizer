import logging
from unittest import TestCase
from unittest.mock import MagicMock

from calculations.domain.services.scenario_warm_timing import log_warm_timings


class ScenarioWarmTimingTests(TestCase):
    def test_log_warm_timings_formats_top_phases_and_detail(self) -> None:
        logger = MagicMock(spec=logging.Logger)
        log_warm_timings(
            logger,
            label="kpi",
            phases={
                "context_ms": 12,
                "sidecar_load_ms": 340,
                "kpi_compute_ms": 910,
                "kpi_save_ms": 45,
                "total_ms": 1320,
            },
            detail={
                "masks_ms": 220,
                "years_loop_ms": 640,
                "charge_npy_read_ms": 180,
            },
            scenario_id=7,
            change="update",
        )

        message = logger.info.call_args.args[0]
        self.assertIn("Scenario rebuild kpi total=1320ms", message)
        self.assertIn("kpi_compute_ms=910ms", message)
        self.assertIn("scenario_id=7", message)
        self.assertIn("detail:", message)
        self.assertIn("years_loop_ms=640ms", message)
