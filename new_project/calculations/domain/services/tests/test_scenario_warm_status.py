from unittest import TestCase
from unittest.mock import patch

from calculations.domain.services.scenario_warm_status import (
    ScenarioWarmStatus,
    _status_to_api,
)


class ScenarioWarmStatusApiTests(TestCase):
    def test_compact_on_disk_does_not_force_done_phase(self) -> None:
        status = ScenarioWarmStatus(
            scenario_id=1,
            phase="compact",
            data_version="dv1",
            rebuild_message=None,
        )
        with patch(
            "calculations.domain.services.scenario_warm_status.try_load_scenario_compute",
            return_value=object(),
        ), patch(
            "calculations.domain.services.scenario_warm_status.is_scenario_compact_on_disk",
            return_value=True,
        ):
            payload = _status_to_api(status)

        self.assertEqual(payload["phase"], "compact")
        self.assertTrue(payload["compact_ready"])
        self.assertIsNone(payload["rebuild_message"])

    def test_done_phase_keeps_rebuild_message(self) -> None:
        message = "Scenario rebuild compact total=15000ms"
        status = ScenarioWarmStatus(
            scenario_id=1,
            phase="done",
            data_version="dv1",
            rebuild_message=message,
        )
        with patch(
            "calculations.domain.services.scenario_warm_status.try_load_scenario_compute",
            return_value=object(),
        ), patch(
            "calculations.domain.services.scenario_warm_status.is_scenario_compact_on_disk",
            return_value=True,
        ):
            payload = _status_to_api(status)

        self.assertEqual(payload["phase"], "done")
        self.assertEqual(payload["rebuild_message"], message)
