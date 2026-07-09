import json
import shutil
from unittest import TestCase
from unittest.mock import patch

import numpy as np

from calculations.domain.services.route_mart_store import MartSidecarView
from calculations.domain.services.scenario_compute_store import (
    BASELINE_RUB_FILENAME,
    METADATA_FILENAME,
    MONEY_FALLOUT_BY_YEAR_FILENAME,
    VOLUME_FALLOUT_BY_YEAR_FILENAME,
    ScenarioComputeBundle,
    compute_fallout_fingerprint,
    is_scenario_fallout_on_disk,
    purge_stale_scenario_compute,
    save_fallout_cache,
    save_scenario_compute,
    save_scenario_fallout_arrays,
    scenario_compute_cache_root,
    scenario_compute_dir,
    try_load_fallout_cache,
)
from calculations.domain.services.scenario_effects_cache import CompactRouteEffects
from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from scenarios.models import Scenario


def _minimal_compact(*, with_fallout: bool = False) -> CompactRouteEffects:
    volume_fallout = money_fallout = None
    if with_fallout:
        volume_fallout = np.array([[0.1, 0.2]], dtype=np.float32)
        money_fallout = np.array([[1.0, 2.0]], dtype=np.float32)
    return CompactRouteEffects(
        years=[2025, 2026],
        dimensions={
            "cargo_group": np.array([0], dtype=np.int32),
            "cargo_code": np.array([0], dtype=np.int32),
            "direction": np.array([0], dtype=np.int32),
            "wagon_kind": np.array([0], dtype=np.int32),
            "transport_type": np.array([0], dtype=np.int32),
            "shipment_category": np.array([0], dtype=np.int32),
            "park_type": np.array([0], dtype=np.int32),
            "holding": np.array([0], dtype=np.int32),
        },
        dimension_labels={
            "cargo_group": ["A"],
            "cargo_code": ["C1"],
            "direction": ["D"],
            "wagon_kind": ["W"],
            "transport_type": ["T"],
            "shipment_category": ["S"],
            "park_type": ["P"],
            "holding": ["H1"],
        },
        baseline_rub=np.array([1.0], dtype=np.float32),
        volume_tons=np.array([3.0], dtype=np.float32),
        base_by_year=np.array([[10.0, 11.0]], dtype=np.float32),
        rules_by_year=np.array([[1.0, 1.5]], dtype=np.float32),
        charge_by_year=np.array([[100.0, 110.0]], dtype=np.float32),
        rule_meta=[],
        rule_by_year=None,
        volume_fallout_by_year=volume_fallout,
        money_fallout_by_year=money_fallout,
    )


class ScenarioComputeFalloutIoTests(TestCase):
    def setUp(self) -> None:
        shutil.rmtree(scenario_compute_cache_root(), ignore_errors=True)

    def tearDown(self) -> None:
        shutil.rmtree(scenario_compute_cache_root(), ignore_errors=True)

    def test_save_fallout_arrays_appends_without_touching_compact(self) -> None:
        scenario_id = 42
        data_version = "dv1"
        compact = _minimal_compact(with_fallout=False)
        save_scenario_compute(
            scenario_id=scenario_id,
            data_version=data_version,
            bundle=ScenarioComputeBundle(
                compact=compact,
                global_totals=GlobalTotals(),
                filter_options={},
                skipped_charge=0,
                routes_without_volume=0,
            ),
        )
        cache_dir = scenario_compute_dir(
            scenario_id=scenario_id,
            data_version=data_version,
        )
        baseline_path = cache_dir / BASELINE_RUB_FILENAME
        baseline_mtime = baseline_path.stat().st_mtime

        volume_fallout = np.array([[0.5, 0.6]], dtype=np.float32)
        money_fallout = np.array([[5.0, 6.0]], dtype=np.float32)
        save_scenario_fallout_arrays(
            scenario_id=scenario_id,
            data_version=data_version,
            volume_fallout_by_year=volume_fallout,
            money_fallout_by_year=money_fallout,
        )

        self.assertTrue(is_scenario_fallout_on_disk(
            scenario_id=scenario_id,
            data_version=data_version,
        ))
        metadata = json.loads((cache_dir / METADATA_FILENAME).read_text(encoding="utf-8"))
        self.assertTrue(metadata.get("fallout_ready"))
        np.testing.assert_array_equal(
            np.load(cache_dir / VOLUME_FALLOUT_BY_YEAR_FILENAME, mmap_mode=None),
            volume_fallout,
        )
        np.testing.assert_array_equal(
            np.load(cache_dir / MONEY_FALLOUT_BY_YEAR_FILENAME, mmap_mode=None),
            money_fallout,
        )
        self.assertEqual(baseline_path.stat().st_mtime, baseline_mtime)

    def test_fallout_disk_cache_roundtrip(self) -> None:
        scenario = Scenario(
            elasticity_set_id=7,
            retention_coefficient_mode="combined",
            consider_enterprise_load=True,
        )
        initial = np.array([100.0, 200.0], dtype=np.float32)
        charge = np.array([[100.0, 110.0], [200.0, 220.0]], dtype=np.float32)
        turnover = np.array([[1.0, 1.0], [1.0, 1.0]], dtype=np.float32)
        fingerprint = compute_fallout_fingerprint(
            scenario=scenario,
            initial_charge=initial,
            charge_by_year=charge,
            turnover_coef=turnover,
        )
        volume = np.array([[0.1, 0.2], [0.3, 0.4]], dtype=np.float32)
        money = np.array([[1.0, 2.0], [3.0, 4.0]], dtype=np.float32)
        save_fallout_cache(
            scenario_id=99,
            fingerprint=fingerprint,
            volume_fallout_by_year=volume,
            money_fallout_by_year=money,
        )
        loaded = try_load_fallout_cache(
            scenario_id=99,
            fingerprint=fingerprint,
            n_routes=2,
            n_years=2,
        )
        self.assertIsNotNone(loaded)
        assert loaded is not None
        np.testing.assert_array_equal(loaded[0], volume)
        np.testing.assert_array_equal(loaded[1], money)

    def test_purge_stale_keeps_fallout_cache_directory(self) -> None:
        scenario_id = 5
        keep = "keep_ver"
        stale = "stale_ver"
        scenario_compute_dir(scenario_id=scenario_id, data_version=keep).mkdir(
            parents=True,
            exist_ok=True,
        )
        scenario_compute_dir(scenario_id=scenario_id, data_version=stale).mkdir(
            parents=True,
            exist_ok=True,
        )
        fallout_cache = (
            scenario_compute_cache_root() / str(scenario_id) / "fallout_cache" / "abc"
        )
        fallout_cache.mkdir(parents=True, exist_ok=True)

        removed = purge_stale_scenario_compute(
            scenario_id=scenario_id,
            keep_data_version=keep,
        )
        self.assertEqual(removed, 1)
        self.assertTrue(
            scenario_compute_dir(scenario_id=scenario_id, data_version=keep).is_dir(),
        )
        self.assertFalse(
            scenario_compute_dir(scenario_id=scenario_id, data_version=stale).is_dir(),
        )
        self.assertTrue(fallout_cache.is_dir())

    def test_deferred_path_uses_fallout_append_not_second_full_save(self) -> None:
        from calculations.domain.services.scenario_effects_deferred import (
            DeferredFullComputeJob,
            _run_deferred_full_compute,
        )
        from calculations.domain.services.scenario_effects_formatting import GlobalTotals

        save_calls: list[str] = []
        fallout_calls: list[str] = []

        def _track_save(**kwargs):
            save_calls.append("save")
            return scenario_compute_dir(
                scenario_id=kwargs["scenario_id"],
                data_version=kwargs["data_version"],
            )

        def _track_fallout(**kwargs):
            fallout_calls.append("fallout")
            cache_dir = scenario_compute_dir(
                scenario_id=kwargs["scenario_id"],
                data_version=kwargs["data_version"],
            )
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / METADATA_FILENAME).write_text(
                json.dumps({"kpi_only": False, "fallout_ready": False}),
                encoding="utf-8",
            )
            return cache_dir

        sidecar = MartSidecarView(
            column_arrays={
                "freight_charge_rub": np.array([100.0], dtype=np.float32),
                "transport_volume_tons": np.array([1.0], dtype=np.float32),
            },
        )

        job = DeferredFullComputeJob(
            cache_key="ck",
            scenario_id=1,
            route_set_id=1,
            data_version="dv",
            years=[2025, 2026],
            base_coef_by_year={2025: 1.0, 2026: 1.0},
            rule_specs=[],
            parquet_path="fake.parquet",
            mask_cache_dir_path="",
            mart_meta=None,
            global_totals=GlobalTotals(),
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
            consider_demand_elasticity=True,
            elasticity_set_id=1,
            model_rows=[],
        )

        arrays = type(
            "Arrays",
            (),
            {
                "initial": np.array([100.0], dtype=np.float32),
                "base_by_year": np.zeros((1, 2), dtype=np.float32),
                "rules_by_year_arr": np.ones((1, 2), dtype=np.float32),
                "charge_by_year": np.array([[100.0, 110.0]], dtype=np.float32),
                "rule_meta": [],
                "rule_by_year": None,
                "turnover_coef": np.ones((1, 2), dtype=np.float32),
            },
        )()

        with patch(
            "calculations.domain.services.scenario_effects_deferred._job_data_version_stale",
            return_value=False,
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.ensure_compute_sidecars",
            return_value=True,
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.load_mart_sidecar",
            return_value=(sidecar, {}),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.compute_arrays_full",
            return_value=(GlobalTotals(), {}, arrays),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.prepare_compact_inputs",
            return_value=({}, {}, np.array([1.0], dtype=np.float32)),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.build_compact_from_arrays",
            return_value=_minimal_compact(),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.save_scenario_compute",
            side_effect=_track_save,
        ), patch(
            "calculations.domain.services.scenario_compute_store.save_scenario_fallout_arrays",
            side_effect=_track_fallout,
        ), patch(
            "calculations.domain.services.scenario_compute_store.compute_fallout_fingerprint",
            return_value="fp1",
        ), patch(
            "calculations.domain.services.scenario_compute_store.try_load_fallout_cache",
            return_value=None,
        ), patch(
            "calculations.domain.services.elasticity_fallout_compute.compute_fallout_arrays",
            return_value=(
                np.zeros((1, 2), dtype=np.float32),
                np.zeros((1, 2), dtype=np.float32),
                type("Stats", (), {"to_timings": lambda self: {}})(),
            ),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.update_payload_compact",
        ), patch(
            "calculations.domain.services.scenario_effects_cache.update_payload_fallout_ready",
        ), patch(
            "calculations.domain.services.scenario_warm_status.update_warm_status",
        ), patch(
            "calculations.domain.services.scenario_effects_cache.set_scenario_effects_revision",
        ), patch(
            "calculations.domain.services.scenario_compute_store.save_fallout_cache",
        ), patch(
            "calculations.domain.services.scenario_effects_compute.build_turnover_coef_matrix",
            return_value=np.ones((1, 2), dtype=np.float32),
        ):
            _run_deferred_full_compute(job)

        self.assertEqual(save_calls, ["save"])
        self.assertEqual(fallout_calls, ["fallout"])

    def test_save_compact_and_fallout_timings_are_split(self) -> None:
        from calculations.domain.services.scenario_effects_deferred import (
            DeferredFullComputeJob,
            _run_deferred_full_compute,
        )
        from calculations.domain.services.scenario_effects_formatting import GlobalTotals

        captured_phases: dict[str, int] = {}

        def _capture_log(_logger, *, label, phases, detail=None, **kwargs):
            if label == "compact":
                captured_phases.update(phases)

        sidecar = MartSidecarView(
            column_arrays={
                "freight_charge_rub": np.array([100.0], dtype=np.float32),
                "transport_volume_tons": np.array([1.0], dtype=np.float32),
            },
        )
        arrays = type(
            "Arrays",
            (),
            {
                "initial": np.array([100.0], dtype=np.float32),
                "base_by_year": np.zeros((1, 2), dtype=np.float32),
                "rules_by_year_arr": np.ones((1, 2), dtype=np.float32),
                "charge_by_year": np.array([[100.0, 110.0]], dtype=np.float32),
                "rule_meta": [],
                "rule_by_year": None,
                "turnover_coef": np.ones((1, 2), dtype=np.float32),
            },
        )()
        job = DeferredFullComputeJob(
            cache_key="ck",
            scenario_id=2,
            route_set_id=1,
            data_version="dv2",
            years=[2025, 2026],
            base_coef_by_year={2025: 1.0, 2026: 1.0},
            rule_specs=[],
            parquet_path="fake.parquet",
            mask_cache_dir_path="",
            mart_meta=None,
            global_totals=GlobalTotals(),
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
            consider_demand_elasticity=True,
            elasticity_set_id=1,
            model_rows=[],
        )

        with patch(
            "calculations.domain.services.scenario_effects_deferred._job_data_version_stale",
            return_value=False,
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.ensure_compute_sidecars",
            return_value=True,
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.load_mart_sidecar",
            return_value=(sidecar, {}),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.compute_arrays_full",
            return_value=(GlobalTotals(), {}, arrays),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.prepare_compact_inputs",
            return_value=({}, {}, np.array([1.0], dtype=np.float32)),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.build_compact_from_arrays",
            return_value=_minimal_compact(),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.save_scenario_compute",
            return_value=scenario_compute_dir(scenario_id=2, data_version="dv2"),
        ), patch(
            "calculations.domain.services.scenario_compute_store.save_scenario_fallout_arrays",
            return_value=scenario_compute_dir(scenario_id=2, data_version="dv2"),
        ), patch(
            "calculations.domain.services.scenario_compute_store.compute_fallout_fingerprint",
            return_value="fp2",
        ), patch(
            "calculations.domain.services.scenario_compute_store.try_load_fallout_cache",
            return_value=None,
        ), patch(
            "calculations.domain.services.elasticity_fallout_compute.compute_fallout_arrays",
            return_value=(
                np.zeros((1, 2), dtype=np.float32),
                np.zeros((1, 2), dtype=np.float32),
                type("Stats", (), {"to_timings": lambda self: {}})(),
            ),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.update_payload_compact",
        ), patch(
            "calculations.domain.services.scenario_effects_cache.update_payload_fallout_ready",
        ), patch(
            "calculations.domain.services.scenario_warm_status.update_warm_status",
        ), patch(
            "calculations.domain.services.scenario_effects_cache.set_scenario_effects_revision",
        ), patch(
            "calculations.domain.services.scenario_compute_store.save_fallout_cache",
        ), patch(
            "calculations.domain.services.scenario_effects_compute.build_turnover_coef_matrix",
            return_value=np.ones((1, 2), dtype=np.float32),
        ), patch(
            "calculations.domain.services.scenario_effects_deferred.log_warm_timings",
            side_effect=_capture_log,
        ):
            cache_dir = scenario_compute_dir(scenario_id=2, data_version="dv2")
            cache_dir.mkdir(parents=True, exist_ok=True)
            (cache_dir / METADATA_FILENAME).write_text(
                json.dumps({"kpi_only": False, "fallout_ready": False}),
                encoding="utf-8",
            )
            _run_deferred_full_compute(job)

        self.assertIn("save_compact_ms", captured_phases)
        self.assertIn("save_fallout_ms", captured_phases)
        self.assertEqual(
            captured_phases["save_ms"],
            captured_phases["save_compact_ms"] + captured_phases["save_fallout_ms"],
        )
