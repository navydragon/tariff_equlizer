from __future__ import annotations

from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from calculations.domain.dto.scenario_effects_cube import ScenarioEffectsCubeRequestDTO
from calculations.domain.services.scenario_effects_cube_job import (
    CubeAggregateJob,
    _job_cache_key,
    _save_job,
    get_cube_job_status,
    start_cube_aggregate_job,
)
from calculations.tests import TariffLoadServiceTestMixin

User = get_user_model()


class ScenarioEffectsCubeJobTests(TariffLoadServiceTestMixin, TestCase):
    def setUp(self) -> None:
        super().setUp()
        self.client = Client()
        self.client.force_login(self.user)

    def test_progress_callback_invoked_during_aggregate(self) -> None:
        from calculations.domain.services.scenario_effects_cube import (
            ScenarioEffectsCubeService,
        )

        progress: list[tuple[int, str]] = []

        def on_progress(pct: int, message: str) -> None:
            progress.append((pct, message))

        service = ScenarioEffectsCubeService()
        with patch.object(
            ScenarioEffectsCubeService,
            "_build_effect_slices",
            return_value=[("base", "Базовая индексация"), ("rules_total", "Итого")],
        ), patch.object(
            ScenarioEffectsCubeService,
            "_aggregate_groups",
            return_value={
                "base": {("ИТОГО",): {2026: 1}},
                "rules_total": {("ИТОГО",): {2026: 2}},
            },
        ), patch.object(
            ScenarioEffectsCubeService,
            "_build_rows",
            return_value=[],
        ), patch(
            "calculations.domain.services.scenario_effects_cube.get_payload_ready",
        ) as mock_payload_ready:
            mock_payload_ready.return_value = type(
                "Payload",
                (),
                {
                    "compact": object(),
                    "years": [2026],
                    "facts": [],
                    "user_id": self.user.id,
                    "scenario_id": self.scenario.id,
                },
            )()
            result, errors, _meta = service.aggregate(
                scenario=self.scenario,
                user_id=self.user.id,
                request=ScenarioEffectsCubeRequestDTO(cache_key="test-key"),
                on_progress=on_progress,
            )

        self.assertEqual(errors, [])
        self.assertIsNotNone(result)
        self.assertTrue(any(pct >= 90 for pct, _msg in progress))
        self.assertTrue(any("Агрегация" in msg or "Подготовка" in msg for _pct, msg in progress))

    def test_get_cube_job_status_requires_owner(self) -> None:
        job = CubeAggregateJob(
            job_id="job-1",
            user_id=self.user.id,
            scenario_id=self.scenario.id,
            phase="aggregating",
            progress_pct=42,
            message="Агрегация…",
        )
        _save_job(job)

        status = get_cube_job_status(job_id="job-1", user_id=self.user.id)
        assert status is not None
        self.assertEqual(status["progress_pct"], 42)
        self.assertFalse(status["done"])

        foreign = User.objects.create_user(login="foreign2", password="pass")
        self.assertIsNone(get_cube_job_status(job_id="job-1", user_id=foreign.id))

    @patch(
        "calculations.domain.services.scenario_effects_cube_job._run_cube_aggregate_job",
    )
    def test_start_cube_job_api_returns_job_id(self, mock_run) -> None:
        job_id, errors = start_cube_aggregate_job(
            scenario=self.scenario,
            user_id=self.user.id,
            request=ScenarioEffectsCubeRequestDTO(cache_key="cache-1"),
        )
        self.assertEqual(errors, [])
        self.assertIsNotNone(job_id)

        response = self.client.post(
            reverse("calculations:scenario_effects_cube_start_api"),
            data={
                "scenario_id": self.scenario.id,
                "cache_key": "cache-1",
                "group_by": "cargo_group",
                "group_by_inner": "none",
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertIn("job_id", payload)

    def test_cube_status_api_returns_progress(self) -> None:
        job = CubeAggregateJob(
            job_id="job-status",
            user_id=self.user.id,
            scenario_id=self.scenario.id,
            phase="aggregating",
            progress_pct=55,
            message="Агрегация: правило 10/200",
        )
        from django.core.cache import cache

        cache.set(_job_cache_key(job_id=job.job_id), job, 3600)

        response = self.client.post(
            reverse("calculations:scenario_effects_cube_status_api"),
            data={"job_id": "job-status"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["progress_pct"], 55)
        self.assertEqual(payload["message"], "Агрегация: правило 10/200")
        self.assertFalse(payload["done"])

    def test_cube_export_from_completed_job(self) -> None:
        result = {
            "years": [2026, 2027],
            "total_column_label": "2026–2027",
            "unit": "млрд руб.",
            "group_by_label": "Группа груза",
            "group_by_inner_label": None,
            "table": {
                "rows": [
                    {
                        "group_label": "Уголь",
                        "group_inner_label": None,
                        "effect_label": "Базовая индексация",
                        "years": {"2026": "1.000", "2027": "2.000"},
                        "total": "3.000",
                    },
                ],
            },
        }
        job = CubeAggregateJob(
            job_id="job-export",
            user_id=self.user.id,
            scenario_id=self.scenario.id,
            phase="done",
            progress_pct=100,
            message="Готово",
            result=result,
        )
        from django.core.cache import cache

        cache.set(_job_cache_key(job_id=job.job_id), job, 3600)

        response = self.client.post(
            reverse("calculations:scenario_effects_cube_export_api"),
            data={"job_id": "job-export"},
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        self.assertIn(
            "spreadsheetml",
            response["Content-Type"],
        )
        self.assertGreater(len(response.content), 100)
