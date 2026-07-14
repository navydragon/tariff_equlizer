from django.test import SimpleTestCase
import pandas as pd

from calculations.domain.services.route_effects_loader import normalize_route_dimensions


class NormalizeRouteDimensionsCargoCode3Tests(SimpleTestCase):
    def test_formats_numeric_cargo_code_3_values(self) -> None:
        df = pd.DataFrame(
            {
                "cargo_group": ["Группа", "Группа", "Группа", "Группа"],
                "cargo_code": ["016612", "016612", "016612", "016612"],
                "direction_raw": ["", "", "", ""],
                "shipper_holding": ["", "", "", ""],
                "cargo_code_3": [16, "32", "016", 16.0],
                "cargo_code_izpod_3": [21, "022", "", 161.0],
            },
        )

        normalize_route_dimensions(df)

        self.assertEqual(df["cargo_code_3"].tolist(), ["016", "032", "016", "016"])
        self.assertEqual(
            df["cargo_code_izpod_3"].tolist(),
            ["021", "022", "", "161"],
        )
