from decimal import Decimal

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings

from assistant.domain.dto.chat import ChatRequestDTO
from assistant.domain.services.chat import AssistantChatService
from core.models import (
    Cargo,
    CargoGroup,
    MessageType,
    RailRoad,
    Region,
    Route,
    RouteSet,
    ShipmentType,
    Station,
    WagonKind,
)
from scenarios.models import BTDCategory, BTDCategoryValue, Scenario

User = get_user_model()


class AssistantChatPresetTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="assistant_chat_user", password="pass")
        self.route_set = RouteSet.objects.create(name="RS", code="RS_CHAT")
        self.scenario = Scenario.objects.create(
            name="Chat scenario",
            start_year=2025,
            end_year=2026,
            route_set=self.route_set,
            author=self.user,
        )
        self.route = self._create_route()
        category = BTDCategory.objects.create(
            name="Индексация",
            scenario=self.scenario,
            position=1,
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=category,
            year=2025,
            value=Decimal("1.0000"),
        )
        BTDCategoryValue.objects.create(
            scenario=self.scenario,
            category=category,
            year=2026,
            value=Decimal("1.0500"),
        )
        self.service = AssistantChatService()

    def _create_route(self) -> Route:
        cargo_group, _ = CargoGroup.objects.get_or_create(
            code=92,
            defaults={"name": "Group", "position": 1},
        )
        cargo, _ = Cargo.objects.get_or_create(
            code=9201,
            defaults={"name": "Cargo 9201", "cargo_group": cargo_group},
        )
        railroad, _ = RailRoad.objects.get_or_create(
            code="92",
            defaults={"name": "Road"},
        )
        region, _ = Region.objects.get_or_create(
            short_name="RB",
            full_name="Region B",
            type="область",
        )
        origin, _ = Station.objects.get_or_create(
            esr_code=920001,
            defaults={
                "short_name": "A",
                "full_name": "Station A",
                "region": region,
                "railroad": railroad,
            },
        )
        destination, _ = Station.objects.get_or_create(
            esr_code=920002,
            defaults={
                "short_name": "B",
                "full_name": "Station B",
                "region": region,
                "railroad": railroad,
            },
        )
        wagon_kind, _ = WagonKind.objects.get_or_create(
            code="WK92",
            defaults={"name": "Wagon"},
        )
        shipment_type, _ = ShipmentType.objects.get_or_create(
            code="ST92",
            defaults={"name": "Shipment"},
        )
        message_type, _ = MessageType.objects.get_or_create(
            code="MT_CHAT",
            defaults={"name": "Внутр. перевозки"},
        )
        return Route.objects.create(
            route_set=self.route_set,
            cargo=cargo,
            origin_station=origin,
            destination_station=destination,
            wagon_kind=wagon_kind,
            shipment_type=shipment_type,
            message_type=message_type,
            route_code="CHAT-001",
            rzd_cost_total_per_ton=Decimal("1000.00"),
            production_cost_per_ton=Decimal("500.00"),
            operators_cost_per_ton=Decimal("100.00"),
            market_price_per_ton=Decimal("2000.00"),
        )

    def _dto(self, *, preset: str = "route_summary") -> ChatRequestDTO:
        return ChatRequestDTO.from_payload(
            {
                "page": "route_analysis",
                "message": "",
                "preset": preset,
                "context": {
                    "scenario_id": self.scenario.id,
                    "route_id": self.route.id,
                },
            },
        )

    def test_preset_route_summary(self):
        response, errors = self.service.chat(user=self.user, request_dto=self._dto())
        self.assertEqual(errors, [])
        self.assertIsNotNone(response)
        self.assertEqual(response.mode, "preset")
        self.assertIn("CHAT-001", response.answer)
        self.assertIn("get_route_summary", response.tools_used)

    def test_preset_kpi(self):
        response, errors = self.service.chat(
            user=self.user,
            request_dto=self._dto(preset="explain_kpi"),
        )
        self.assertEqual(errors, [])
        self.assertEqual(response.mode, "preset")
        self.assertIn("KPI", response.answer)
        self.assertIn("get_kpi_summary", response.tools_used)

    @override_settings(ASSISTANT_LLM_ENABLED=False, ASSISTANT_LLM_API_KEY="")
    def test_free_text_without_llm(self):
        dto = ChatRequestDTO.from_payload(
            {
                "page": "route_analysis",
                "message": "Почему падает маржа?",
                "context": {
                    "scenario_id": self.scenario.id,
                    "route_id": self.route.id,
                },
            },
        )
        response, errors = self.service.chat(user=self.user, request_dto=dto)
        self.assertIsNone(response)
        self.assertTrue(errors)
        self.assertIn("LLM выключен", errors[0])

    def test_chat_api_preset(self):
        client = Client()
        client.force_login(self.user)
        response = client.post(
            "/assistant/api/chat/",
            data={
                "page": "route_analysis",
                "preset": "route_summary",
                "context": {
                    "scenario_id": self.scenario.id,
                    "route_id": self.route.id,
                },
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertTrue(payload["success"])
        self.assertEqual(payload["mode"], "preset")
        self.assertIn("CHAT-001", payload["answer"])

    @override_settings(ASSISTANT_LLM_ENABLED=False)
    def test_chat_api_llm_disabled(self):
        client = Client()
        client.force_login(self.user)
        response = client.post(
            "/assistant/api/chat/",
            data={
                "page": "route_analysis",
                "message": "Свободный вопрос",
                "context": {
                    "scenario_id": self.scenario.id,
                    "route_id": self.route.id,
                },
            },
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertFalse(payload["success"])
        self.assertTrue(
            any("LLM" in e or "быстрые вопросы" in e for e in payload["errors"]),
        )
