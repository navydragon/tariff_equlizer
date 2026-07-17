from __future__ import annotations

from decimal import Decimal
from unittest.mock import patch

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from calculations.domain.services.scenario_effects_compute import (
    RuleComputeSpec,
    compute_arrays_full,
)


class ScenarioEffectsComputeRuleBreakdownTests(SimpleTestCase):
    @patch(
        (
            "calculations.domain.services.scenario_effects_compute."
            "_prepare_rules_state"
        ),
    )
    def test_rule_breakdown_uses_float32_dtype(
        self,
        prepare_rules_state_mock,
    ) -> None:
        sidecar = pd.DataFrame({"freight_charge_rub": [100.0, 200.0]})
        prepare_rules_state_mock.return_value = (
            np.array(
                [
                    [1.0, 1.05],
                    [1.0, 1.05],
                ],
                dtype=np.float64,
            ),
            [(1, "Rule 1")],
            [np.array([True, False])],
            [[1.0, 1.05]],
            {},
        )

        _totals, _timings, arrays = compute_arrays_full(
            sidecar,
            years=[2025, 2026],
            base_coef_by_year={2025: Decimal("1"), 2026: Decimal("1")},
            rule_specs=[
                RuleComputeSpec(
                    id=1,
                    name="Rule 1",
                    base_percent=100.0,
                    conditions=[],
                    year_values={2026: 1.05},
                )
            ],
            route_set_id=1,
            mart_meta=None,
            include_rule_by_year=True,
            include_fallout=False,
        )

        assert arrays is not None
        assert arrays.rule_by_year is not None
        self.assertEqual(arrays.rule_by_year.dtype, np.float32)
