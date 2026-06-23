from decimal import Decimal

import numpy as np
import pandas as pd
from django.test import SimpleTestCase

from calculations.domain.services.route_mart_store import build_turnover_coef_array
from core.domain.route.turnover_coefficients import route_field_for_year


class RouteMartTurnoverCoefTests(SimpleTestCase):
    def test_build_turnover_coef_array_fills_missing_with_one(self) -> None:
        df = pd.DataFrame(
            {
                route_field_for_year(2025): [Decimal("1.050"), None],
                route_field_for_year(2026): [None, Decimal("0.900")],
            },
        )
        matrix = build_turnover_coef_array(df)
        self.assertEqual(matrix.shape, (2, 6))
        np.testing.assert_allclose(matrix[0], [1.05, 1.0, 1.0, 1.0, 1.0, 1.0], rtol=0, atol=0.001)
        np.testing.assert_allclose(matrix[1], [1.0, 0.9, 1.0, 1.0, 1.0, 1.0], rtol=0, atol=0.001)
