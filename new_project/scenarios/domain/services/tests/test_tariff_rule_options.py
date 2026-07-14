from django.test import SimpleTestCase

import pandas as pd

from calculations.domain.services.pandas_tariff_conditions import (
    _label_codes,
    build_rule_mask_numpy,
)
from calculations.domain.services.route_mart_store import (
    MartMeta,
    _factorize_mask_column,
    _normalize_mask_label_values,
)
from scenarios.domain.services.tariff_rule_options import mask_sidecar_option_items


class CargoCode3OptionFormattingTests(SimpleTestCase):
    def test_normalize_mask_label_values_restores_leading_zero(self) -> None:
        labels = _normalize_mask_label_values([16, "32", "016"], column="cargo_code_3")
        self.assertEqual(labels, ["016", "032"])

    def test_label_codes_matches_sixteen_and_zero_sixteen(self) -> None:
        labels = ["16", "32", "161"]
        codes_from_short = _label_codes(["16"], labels, column="cargo_code_3")
        codes_from_padded = _label_codes(["016"], labels, column="cargo_code_3")
        self.assertEqual(codes_from_short, codes_from_padded)
        self.assertEqual(codes_from_short, [0])

    def test_mask_sidecar_option_items_formats_db_fallback_values(self) -> None:
        from unittest.mock import patch

        with patch(
            "scenarios.domain.services.tariff_rule_options.distinct_mask_sidecar_labels",
            return_value=None,
        ), patch(
            "scenarios.domain.services.tariff_rule_options._distinct_route_values",
            return_value=["16", "161", "810"],
        ):
            items = mask_sidecar_option_items(route_set_id=1, column="cargo_code_3")

        self.assertEqual(
            items,
            [
                {"value": "016", "text": "016"},
                {"value": "161", "text": "161"},
                {"value": "810", "text": "810"},
            ],
        )

    def test_factorize_mask_column_keeps_empty_aligned_with_labels(self) -> None:
        series = pd.Series(["", "161", "0", "161", ""])
        factored = _factorize_mask_column(series, "cargo_code_izpod_3")
        assert factored is not None
        codes, labels = factored
        self.assertEqual(labels, ["", "161", "000"])
        self.assertEqual(codes.tolist(), [0, 1, 2, 1, 0])
        matched = _label_codes(["161"], labels, column="cargo_code_izpod_3")
        self.assertEqual(matched, [1])
        self.assertEqual(int((codes == matched[0]).sum()), 2)

    def test_missing_cargo_code_izpod_3_mask_fails_closed(self) -> None:
        df = pd.DataFrame(
            {
                "cargo_code_3": ["421", "161"],
                "freight_charge_rub": [1.0, 2.0],
            },
        )
        mask = build_rule_mask_numpy(
            df,
            [
                {
                    "parameter": "cargo_code_izpod_3",
                    "operator": "include",
                    "values": ["161"],
                },
            ],
            mart_meta=MartMeta(dimension_labels={}),
        )
        self.assertFalse(bool(mask.any()))
