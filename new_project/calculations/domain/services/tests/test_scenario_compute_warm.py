from __future__ import annotations

from unittest.mock import patch

from django.core.cache import cache
from django.test import TestCase

from calculations.domain.services.scenario_compute_store import (
    purge_scenario_compute,
    scenario_compute_cache_root,
    scenario_compute_dir,
    save_scenario_compute_kpi_only,
)
from calculations.domain.services.scenario_compute_warm import (
    warm_scenario_compute,
)
from calculations.domain.services.scenario_effects_formatting import (
    GlobalTotals,
)
from calculations.domain.services.scenario_warm_status import (
    clear_warm_status,
    init_warm_status,
    mark_warm_error,
    warm_status_cache_key,
)
from core.models import RouteSet, User
from scenarios.models import Scenario


class ScenarioComputeWarmForceTests(TestCase):
    def setUp(self) -> None:
        cache.clear()

    def tearDown(self) -> None:
        cache.clear()

    def test_purge_scenario_compute_removes_disk_cache(self) -> None:
        scenario_id = 999001
        cache_dir = scenario_compute_dir(
            scenario_id=scenario_id,
            data_version="deadbeef",
        )
        save_scenario_compute_kpi_only(
            scenario_id=scenario_id,
            data_version="deadbeef",
            years=[2026],
            global_totals=GlobalTotals(),
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
            early_group_snapshot=None,
        )
        self.assertTrue(cache_dir.is_dir())

        removed = purge_scenario_compute(scenario_id=scenario_id)
        self.assertTrue(removed)
        self.assertFalse(
            (scenario_compute_cache_root() / str(scenario_id)).exists()
        )

    def test_clear_warm_status_removes_error_from_cache(self) -> None:
        scenario_id = 999002
        init_warm_status(
            scenario_id=scenario_id,
            data_version="v1",
            mask_changed=False,
            rule_id=None,
            phase="error",
        )
        mark_warm_error(
            scenario_id=scenario_id,
            error="Ошибка фоновой сборки детализации",
        )
        self.assertIsNotNone(
            cache.get(warm_status_cache_key(scenario_id=scenario_id))
        )

        clear_warm_status(scenario_id=scenario_id)
        self.assertIsNone(
            cache.get(warm_status_cache_key(scenario_id=scenario_id))
        )

    @patch(
        "calculations.domain.services.scenario_compute_warm.wait_scenario_detail_ready",
        return_value=(True, True, 42),
    )
    @patch(
        "calculations.domain.services.scenario_compute_warm.warm_scenario_kpi_snapshot",
    )
    @patch(
        "calculations.domain.services.scenario_compute_warm.resolve_warm_data_version",
        return_value="forced-version",
    )
    def test_force_rebuild_clears_cache_and_warm_status(
        self,
        resolve_version_mock,
        warm_snapshot_mock,
        wait_detail_mock,
    ) -> None:
        user = User.objects.create_user(
            login="force_warm_user",
            password="pass",
        )
        route_set = RouteSet.objects.create(name="Force warm RS", code="FW_RS")
        scenario = Scenario.objects.create(
            name="Force warm scenario",
            author=user,
            route_set=route_set,
        )
        scenario_id = scenario.id
        cache_dir = scenario_compute_dir(
            scenario_id=scenario_id,
            data_version="stale",
        )
        save_scenario_compute_kpi_only(
            scenario_id=scenario_id,
            data_version="stale",
            years=[2026],
            global_totals=GlobalTotals(),
            filter_options={},
            skipped_charge=0,
            routes_without_volume=0,
            early_group_snapshot=None,
        )
        mark_warm_error(
            scenario_id=scenario_id,
            error="Ошибка фоновой сборки детализации",
        )

        failed = warm_scenario_compute(
            scenario_id=scenario_id,
            force=True,
            write=lambda _message: None,
        )

        self.assertEqual(failed, 0)
        self.assertFalse(cache_dir.exists())
        warm_snapshot_mock.assert_called_once_with(
            scenario_id=scenario_id,
            include_rule_breakdown=False,
        )
        wait_detail_mock.assert_called_once()
        status = cache.get(warm_status_cache_key(scenario_id=scenario_id))
        self.assertIsNone(status)

    @patch(
        "calculations.domain.services.scenario_compute_warm.wait_scenario_detail_ready",
        return_value=(True, True, 42),
    )
    @patch(
        "calculations.domain.services.scenario_compute_warm.warm_scenario_kpi_snapshot",
    )
    @patch(
        "calculations.domain.services.scenario_compute_warm.resolve_warm_data_version",
        return_value="forced-version",
    )
    def test_force_rebuild_can_request_rule_breakdown(
        self,
        _resolve_version_mock,
        warm_snapshot_mock,
        _wait_detail_mock,
    ) -> None:
        user = User.objects.create_user(
            login="force_breakdown_user",
            password="pass",
        )
        route_set = RouteSet.objects.create(
            name="Force breakdown RS",
            code="FB_RS",
        )
        scenario = Scenario.objects.create(
            name="Force breakdown scenario",
            author=user,
            route_set=route_set,
        )

        failed = warm_scenario_compute(
            scenario_id=scenario.id,
            force=True,
            include_rule_breakdown=True,
            write=lambda _message: None,
        )

        self.assertEqual(failed, 0)
        warm_snapshot_mock.assert_called_once_with(
            scenario_id=scenario.id,
            include_rule_breakdown=True,
        )
