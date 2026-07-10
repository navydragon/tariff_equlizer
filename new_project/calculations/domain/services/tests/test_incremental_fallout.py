from __future__ import annotations

import json
from decimal import Decimal

import numpy as np
from django.test import TestCase


class IncrementalFalloutComputeTests(TestCase):
    def test_compute_fallout_arrays_supports_route_indices_subset(self) -> None:
        """
        Smoke: route_indices ограничивает loop_routes, а вне subset остаются нули.
        """
        from calculations.domain.services.elasticity_fallout_compute import (
            compute_fallout_arrays,
        )
        from calculations.domain.services.route_mart_store import MartSidecarView
        from core.models import Cargo, CargoGroup, MessageType, RouteSet
        from scenarios.models import ElasticityRule, ElasticityRulePoint, ElasticitySet, Scenario

        # Minimal scenario with elasticity enabled.
        from django.contrib.auth import get_user_model

        User = get_user_model()
        user = User.objects.create_user(login="inc_fallout_user", password="test_pass")
        route_set = RouteSet.objects.create(code="RS_INC", name="RS_INC")
        scenario = Scenario.objects.create(
            name="S",
            description="",
            start_year=2025,
            end_year=2026,
            route_set=route_set,
            author=user,
            consider_demand_elasticity=True,
            retention_coefficient_mode="absolute",
            consider_enterprise_load=True,
        )
        elasticity_set = ElasticitySet.objects.create(name="E", author=user)
        scenario.elasticity_set = elasticity_set
        scenario.save(update_fields=["elasticity_set"])

        cg = CargoGroup.objects.create(code=1, name="Уголь", position=1)
        cargo = Cargo.objects.create(code="1", name="C", cargo_group=cg)
        mt = MessageType.objects.create(code="EXP", name="Экспорт")
        rule = ElasticityRule.objects.create(
            elasticity_set=elasticity_set,
            name="R",
            position=0,
            cargo_group=cg,
            message_type=mt,
        )
        ElasticityRulePoint.objects.create(
            rule=rule,
            marginality=Decimal("0.0"),
            coefficient=Decimal("0.5"),
        )

        # Sidecar 3 routes: only first two in subset, but only second should have ratio!=1 (fallout != 0).
        sidecar = MartSidecarView(
            column_arrays={
                "freight_charge_rub": np.array([100.0, 100.0, 100.0], dtype=np.float32),
                "transport_volume_tons": np.array([1.0, 1.0, 1.0], dtype=np.float32),
                "skip_elasticity": np.array([0, 0, 0], dtype=np.uint8),
                # MartSidecarView path expects numeric codes (see _SOURCE_CODE_TO_NAME).
                "elasticity_source": np.array([1, 1, 1], dtype=np.uint8),
                "message_type_id": np.array([mt.pk, mt.pk, mt.pk], dtype=np.int32),
                "cargo_group_id": np.array([cg.pk, cg.pk, cg.pk], dtype=np.int32),
                "dim_holding": np.array([0, 0, 0], dtype=np.int32),
                "dim_direction": np.array([0, 0, 0], dtype=np.int32),
                # Model-route economics (direct path reads mr_* columns)
                "mr_market_price_per_ton": np.array([1000.0, 1000.0, 1000.0], dtype=np.float32),
                "mr_production_cost_per_ton": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_total_cost_per_ton": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_rzd_cost_total_per_ton": np.array([100.0, 100.0, 100.0], dtype=np.float32),
                "mr_operators_cost_per_ton": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_transshipment_cost_per_ton": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_enterprise_load_coefficient": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_fixed_retention_coefficient": np.array([0.0, 0.0, 0.0], dtype=np.float32),
                "mr_cargo_id": np.array([int(cargo.pk), int(cargo.pk), int(cargo.pk)], dtype=np.int32),
                "mr_message_type_id": np.array([mt.pk, mt.pk, mt.pk], dtype=np.int32),
                "mr_cargo_group_id": np.array([cg.pk, cg.pk, cg.pk], dtype=np.int32),
            },
        )

        years = [2025, 2026]
        initial = np.array([100.0, 100.0, 100.0], dtype=np.float32)
        # only route index 1 changes in year 2026
        charge_by_year = np.array(
            [
                [100.0, 100.0],
                [100.0, 110.0],
                [100.0, 120.0],
            ],
            dtype=np.float32,
        )
        turnover = np.ones_like(charge_by_year, dtype=np.float32)

        vol, money, stats = compute_fallout_arrays(
            sidecar,
            scenario=scenario,
            years=years,
            initial_charge=initial,
            charge_by_year=charge_by_year,
            turnover_coef=turnover,
            model_rows=[],
            route_indices=np.array([0, 1], dtype=np.intp),
        )

        self.assertEqual(stats.loop_routes, 2)
        # route 2 (index 2) not in subset: should be all zeros
        self.assertTrue(np.all(vol[2] == 0))
        self.assertTrue(np.all(money[2] == 0))
        # route 0 in subset but ratio==1: still zeros
        self.assertTrue(np.all(vol[0] == 0))
        self.assertTrue(np.all(money[0] == 0))
        # route 1 changed: should have non-zero in year 2026
        self.assertNotEqual(float(money[1, 1]), 0.0)


class ResolveIncrementalBaseDataVersionTests(TestCase):
    def test_prefers_fallout_ready_snapshot_on_disk_when_revision_missing(self) -> None:
        from calculations.domain.services.scenario_compute_store import (
            METADATA_FILENAME,
            MONEY_FALLOUT_BY_YEAR_FILENAME,
            VOLUME_FALLOUT_BY_YEAR_FILENAME,
            resolve_incremental_base_data_version,
            scenario_compute_dir,
        )

        scenario_id = 90210
        base_version = "base_with_fallout"
        current_version = "current_without_fallout"
        for version, fallout_ready in (
            (base_version, True),
            (current_version, False),
        ):
            cache_dir = scenario_compute_dir(
                scenario_id=scenario_id,
                data_version=version,
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / METADATA_FILENAME).write_text(
                json.dumps(
                    {
                        "kpi_only": False,
                        "fallout_ready": fallout_ready,
                        "years": [2025],
                        "global_totals": {
                            "baseline_total": "0",
                            "base_by_year": {},
                            "rules_by_year": {},
                            "charge_by_year": {},
                        },
                    }
                ),
                encoding="utf-8",
            )
            if fallout_ready:
                np.save(cache_dir / VOLUME_FALLOUT_BY_YEAR_FILENAME, np.zeros((1, 1), dtype=np.float32))
                np.save(cache_dir / MONEY_FALLOUT_BY_YEAR_FILENAME, np.zeros((1, 1), dtype=np.float32))

        resolved = resolve_incremental_base_data_version(
            scenario_id=scenario_id,
            current_data_version=current_version,
            preferred=None,
        )
        self.assertEqual(resolved, base_version)

