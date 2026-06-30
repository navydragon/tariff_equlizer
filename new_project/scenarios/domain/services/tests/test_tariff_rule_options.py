from django.test import SimpleTestCase

from calculations.domain.services.pandas_tariff_conditions import _label_codes
from calculations.domain.services.route_mart_store import _normalize_mask_label_values
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
