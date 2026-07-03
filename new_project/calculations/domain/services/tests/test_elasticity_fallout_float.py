from decimal import Decimal
from unittest import TestCase

from calculations.domain.services.elasticity_fallout_compute import (
    _ModelGroupArrays,
    _weighted_retention,
    _weighted_retention_numpy,
)
from scenarios.domain.repositories.operational_elasticity import ModelRouteEconomicsRow
from scenarios.domain.utils.elasticity_matching import (
    build_float_points_index,
    build_points_index,
    build_rule_index,
)
from scenarios.models import ElasticityRule, Scenario


def _model_row(**kwargs) -> ModelRouteEconomicsRow:
    defaults = {
        "route_id": 1,
        "cargo_id": 101,
        "cargo_group_id": 10,
        "message_type_id": 1,
        "holding": "H1",
        "direction": "D1",
        "transport_volume_tons": Decimal("1000"),
        "market_price_per_ton": Decimal("5000"),
        "production_cost_per_ton": Decimal("3000"),
        "total_cost_per_ton": Decimal("0"),
        "rzd_cost_total_per_ton": Decimal("800"),
        "operators_cost_per_ton": Decimal("100"),
        "transshipment_cost_per_ton": Decimal("50"),
        "enterprise_load_coefficient": Decimal("0.8"),
    }
    defaults.update(kwargs)
    return ModelRouteEconomicsRow(**defaults)


class WeightedRetentionFloatParityTests(TestCase):
    def setUp(self) -> None:
        self.scenario = Scenario(
            consider_demand_elasticity=True,
            elasticity_set_id=1,
            retention_coefficient_mode="relative_to_base",
            consider_enterprise_load=True,
        )
        self.rule = ElasticityRule(
            id=1,
            elasticity_set_id=1,
            cargo_group_id=10,
            cargo_id=None,
            message_type_id=None,
            position=1,
        )
        self.rules = [self.rule]
        self.rule_index = build_rule_index(self.rules)
        point = type(
            "Point",
            (),
            {"marginality": Decimal("0.05"), "coefficient": Decimal("0.95")},
        )()
        point2 = type(
            "Point",
            (),
            {"marginality": Decimal("0.15"), "coefficient": Decimal("0.85")},
        )()
        self.points_index = build_points_index({1: [point, point2]})
        self.float_points_index = build_float_points_index(self.points_index)
        self.rows = [
            _model_row(transport_volume_tons=Decimal("700")),
            _model_row(
                route_id=2,
                cargo_id=102,
                transport_volume_tons=Decimal("300"),
                rzd_cost_total_per_ton=Decimal("900"),
            ),
        ]

    def test_numpy_weighted_retention_matches_decimal_reference(self) -> None:
        group = _ModelGroupArrays.from_rows(self.rows)
        for charge_ratio in (1.0, 1.05, 1.12):
            decimal_value = _weighted_retention(
                self.rows,
                self.scenario,
                self.rules,
                charge_ratio=charge_ratio,
                rule_index=self.rule_index,
                points_index=self.points_index,
            )
            numpy_value = _weighted_retention_numpy(
                group,
                charge_ratio=charge_ratio,
                scenario=self.scenario,
                rule_index=self.rule_index,
                float_points_index=self.float_points_index,
            )
            if decimal_value is None:
                self.assertIsNone(numpy_value)
                continue
            self.assertIsNotNone(numpy_value)
            assert numpy_value is not None
            self.assertAlmostEqual(
                float(decimal_value),
                numpy_value,
                places=6,
                msg=f"charge_ratio={charge_ratio}",
            )
