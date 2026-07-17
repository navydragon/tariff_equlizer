from __future__ import annotations

import json
from unittest.mock import patch

from django.test import TestCase
from django.urls import reverse

from core.models import RouteSet, User
from scenarios.models import Scenario


class ScenarioEffectsComputeApiTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="api_user", password="pass")
        self.route_set = RouteSet.objects.create(name="API RS", code="API_RS")
        self.scenario = Scenario.objects.create(
            name="API scenario",
            author=self.user,
            route_set=self.route_set,
        )
        self.client.force_login(self.user)

    @patch(
        "calculations.views.ScenarioEffectsPandasService.compute_pandas",
        side_effect=PermissionError("denied"),
    )
    def test_compute_pandas_api_returns_json_error_on_exception(
        self,
        _compute_mock,
    ) -> None:
        response = self.client.post(
            reverse("calculations:scenario_effects_compute_pandas_api"),
            data=json.dumps({"scenario_id": self.scenario.id}),
            content_type="application/json",
        )

        self.assertEqual(response.status_code, 500)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertIn("Проверьте права на кеши", payload["errors"][0])
