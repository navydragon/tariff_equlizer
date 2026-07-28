from django.test import SimpleTestCase, override_settings
from pydantic_ai.models.test import TestModel

from assistant.domain.dto.chat import ChatRequestDTO
from assistant.domain.services.agent import build_route_analysis_agent
from assistant.domain.services.deps import AssistantDeps
from assistant.domain.services.llm import AssistantLlmClient
from assistant.domain.tools.registry import ensure_tools_loaded, get_tool


class AssistantLlmDisabledTests(SimpleTestCase):
    @override_settings(ASSISTANT_LLM_ENABLED=False, ASSISTANT_LLM_API_KEY="")
    def test_not_configured_when_disabled(self):
        client = AssistantLlmClient()
        self.assertFalse(client.is_configured())

    @override_settings(ASSISTANT_LLM_ENABLED=True, ASSISTANT_LLM_API_KEY="sk-test")
    def test_configured_when_enabled_with_key(self):
        client = AssistantLlmClient()
        self.assertTrue(client.is_configured())

    def test_chat_request_requires_message_or_preset(self):
        dto = ChatRequestDTO.from_payload(
            {
                "page": "route_analysis",
                "message": "",
                "context": {"scenario_id": 1, "route_id": 2},
            },
        )
        errors = dto.validate()
        self.assertTrue(any("message или preset" in e for e in errors))

    def test_simulate_tool_registered(self):
        ensure_tools_loaded()
        self.assertIsNotNone(get_tool("simulate_parameter_factor"))

    def test_looks_quantitative_requires_param_and_change(self):
        self.assertFalse(
            AssistantLlmClient._looks_quantitative("что будет, если настанет пиздец"),
        )
        self.assertTrue(
            AssistantLlmClient._looks_quantitative(
                "что будет, если цена продажи вырастет в 2 раза?",
            ),
        )
        self.assertFalse(
            AssistantLlmClient._looks_quantitative("расскажи про маршрут"),
        )

    def test_resolve_short_menu_choice(self):
        history = [
            {
                "role": "assistant",
                "content": (
                    "Уточните параметр:\n"
                    "1. Цена\n"
                    "2. Себестоимость\n"
                    "3. Тариф\n"
                ),
            },
        ]
        resolved = AssistantLlmClient._resolve_short_menu_choice("3", history)
        self.assertIn("Тариф", resolved)
        self.assertIn("parameter=base", resolved)
        self.assertIn("НЕ множитель", resolved)
        # Без меню короткий ответ не трогаем
        self.assertEqual(
            AssistantLlmClient._resolve_short_menu_choice("3", []),
            "3",
        )

    def test_extract_menu_options(self):
        options = AssistantLlmClient._extract_menu_options(
            "Выберите:\n1. Цена\n2. Себестоимость\n3. Тариф\n",
        )
        self.assertEqual(options["1"], "Цена")
        self.assertEqual(options["3"], "Тариф")
