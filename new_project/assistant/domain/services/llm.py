from __future__ import annotations

import logging
import re
from typing import Any

from django.conf import settings
from pydantic_ai.exceptions import ModelHTTPError, UnexpectedModelBehavior
from pydantic_ai.messages import (
    ModelRequest,
    ModelResponse,
    TextPart,
    ToolCallPart,
    UserPromptPart,
)

from assistant.domain.services.agent import build_route_analysis_agent
from assistant.domain.services.deps import AssistantDeps

logger = logging.getLogger(__name__)

# «1. Цена» / «2) Себестоимость» / «A. Тариф»
_MENU_OPTION_RE = re.compile(
    r"(?m)^\s*(?:[-*]\s*)?([1-9]|[A-Za-zА-Яа-я])[.)]\s+(.+?)\s*$",
)
_SHORT_CHOICE_RE = re.compile(
    r"^\s*([1-9]|[A-Za-zА-Яа-я])(?:\s*[.)])?\s*$",
    re.IGNORECASE,
)

_PARAM_HINTS = (
    ("цен", "price_rub"),
    ("себестоим", "cost"),
    ("оператор", "oper"),
    ("перевалк", "per"),
    ("индексац", "base"),
    ("правил", "rules"),
    ("тарифн", "rules"),
    ("тариф", "base"),
    ("курс", "fx"),
    ("fx", "fx"),
)


class AssistantLlmClient:
    """Обёртка над Pydantic AI Agent для UI-чата."""

    @property
    def enabled(self) -> bool:
        return bool(getattr(settings, "ASSISTANT_LLM_ENABLED", False))

    @property
    def api_key(self) -> str:
        return getattr(settings, "ASSISTANT_LLM_API_KEY", "") or ""

    @property
    def base_url(self) -> str:
        return (
            getattr(settings, "ASSISTANT_LLM_BASE_URL", "") or "https://api.openai.com/v1"
        ).rstrip("/")

    @property
    def model(self) -> str:
        return getattr(settings, "ASSISTANT_LLM_MODEL", "") or "gpt-4o-mini"

    def is_configured(self) -> bool:
        return self.enabled and bool(self.api_key)

    def run_with_tools(
        self,
        *,
        message: str,
        history: list[dict[str, str]],
        context: dict[str, Any],
    ) -> tuple[str, list[str], dict[str, Any] | None]:
        """
        Возвращает (answer, tools_used, ui_action).
        Бросает RuntimeError при ошибке HTTP/конфигурации.
        """
        if not self.is_configured():
            raise RuntimeError("LLM не настроен")

        deps = AssistantDeps(
            scenario_id=int(context["scenario_id"]),
            route_id=int(context["route_id"]),
            user_id=int(context["user_id"]),
            overrides=context.get("overrides") or {},
        )

        agent = build_route_analysis_agent(
            model_name=self.model,
            api_key=self.api_key,
            base_url=self.base_url,
        )

        resolved_message = self._resolve_short_menu_choice(message, history)
        prompt = self._build_user_prompt(
            message=resolved_message,
            context=context,
            original_message=message,
        )
        message_history = self._to_message_history(history)

        try:
            result = agent.run_sync(
                prompt,
                deps=deps,
                message_history=message_history or None,
            )
        except ModelHTTPError as exc:
            logger.warning("assistant pydantic-ai http error: %s", exc)
            raise RuntimeError(f"LLM API ошибка: {exc}") from exc
        except UnexpectedModelBehavior as exc:
            logger.warning("assistant pydantic-ai unexpected: %s", exc)
            raise RuntimeError(f"Некорректный ответ модели: {exc}") from exc
        except Exception as exc:  # noqa: BLE001
            logger.exception("assistant pydantic-ai failed")
            raise RuntimeError(str(exc)) from exc

        answer = (
            (result.output or "").strip()
            if isinstance(result.output, str)
            else str(result.output or "").strip()
        )
        if not answer:
            raise RuntimeError("LLM вернул пустой ответ")

        tools_used = list(deps.tools_used) or self._tools_from_messages(
            result.all_messages(),
        )

        # Для короткого выбора из меню tools не обязательны — ждём уточнения величины.
        check_message = resolved_message if resolved_message != message else message
        if not tools_used and self._looks_quantitative(check_message):
            raise RuntimeError(
                "Не удалось получить расчёт через tools. "
                "Переформулируйте вопрос или используйте быстрые кнопки ассистента.",
            )

        return answer, tools_used, deps.ui_action

    @classmethod
    def _build_user_prompt(
        cls,
        *,
        message: str,
        context: dict[str, Any],
        original_message: str | None = None,
    ) -> str:
        route_code = context.get("route_code") or ""
        scenario_name = context.get("scenario_name") or ""
        parts = [
            f"Контекст: сценарий «{scenario_name}», маршрут {route_code} "
            f"(scenario_id={context.get('scenario_id')}, route_id={context.get('route_id')}).",
            "",
            f"Вопрос пользователя: {message}",
        ]
        if original_message and original_message.strip() != message.strip():
            parts.append(f"(исходный короткий ввод: «{original_message.strip()}»)")
        return "\n".join(parts)

    @classmethod
    def _resolve_short_menu_choice(
        cls,
        message: str,
        history: list[dict[str, str]],
    ) -> str:
        """
        Если пользователь ответил «3» после меню «1. Цена / 2. … / 3. Тариф»,
        разворачиваем в явный выбор пункта (не множитель).
        """
        match = _SHORT_CHOICE_RE.match((message or "").strip())
        if not match:
            return message

        choice_key = match.group(1).casefold()
        last_assistant = ""
        for item in reversed(history or []):
            if item.get("role") == "assistant" and (item.get("content") or "").strip():
                last_assistant = item["content"]
                break
        if not last_assistant:
            return message

        options = cls._extract_menu_options(last_assistant)
        if choice_key not in options:
            return message

        label = options[choice_key]
        param = cls._guess_parameter(label)
        param_hint = f"parameter={param}" if param else "уточни parameter"
        return (
            f"Пользователь ВЫБРАЛ пункт меню «{label}» ({param_hint}). "
            f"Это НЕ множитель factor={choice_key}. "
            "Не вызывай simulate_parameter_factor, пока не будет явной величины изменения. "
            "Спроси, во сколько раз изменить выбранный параметр, и предложи варианты "
            "словами: «в 1.5 раза», «в 2 раза», «в 3 раза»."
        )

    @staticmethod
    def _extract_menu_options(text: str) -> dict[str, str]:
        options: dict[str, str] = {}
        for match in _MENU_OPTION_RE.finditer(text or ""):
            key = match.group(1).casefold()
            label = match.group(2).strip().rstrip(".")
            if key and label:
                options[key] = label
        return options

    @staticmethod
    def _guess_parameter(label: str) -> str | None:
        text = (label or "").casefold()
        for marker, param in _PARAM_HINTS:
            if marker in text:
                return param
        return None

    @staticmethod
    def _to_message_history(history: list[dict[str, str]]) -> list[ModelRequest | ModelResponse]:
        messages: list[ModelRequest | ModelResponse] = []
        for item in history[-8:]:
            role = item.get("role")
            content = (item.get("content") or "").strip()
            if not content:
                continue
            if role == "user":
                messages.append(ModelRequest(parts=[UserPromptPart(content=content)]))
            elif role == "assistant":
                messages.append(ModelResponse(parts=[TextPart(content=content)]))
        return messages

    @staticmethod
    def _tools_from_messages(messages: list[Any]) -> list[str]:
        used: list[str] = []
        for msg in messages:
            if not isinstance(msg, ModelResponse):
                continue
            for part in msg.parts:
                if isinstance(part, ToolCallPart) and part.tool_name:
                    used.append(part.tool_name)
        return used

    @staticmethod
    def _looks_quantitative(message: str) -> bool:
        """
        Нужен пересчёт через tools только если вопрос про изменение
        конкретного экономического параметра (цена, себестоимость, тариф…).
        Размытые «что если» без параметра — обычный текстовый ответ.
        """
        text = (message or "").casefold()
        # Уже развёрнутый выбор меню без величины — не требуем tools.
        if "это не множитель" in text or "выбрал пункт меню" in text:
            return False
        param_markers = (
            "цен",
            "себестоим",
            "тариф",
            "марж",
            "оператор",
            "перевалк",
            "индексац",
            "правил",
            "курс",
            "fx",
            "price",
            "cost",
            "руб",
            "%",
            "price_rub",
            "parameter=base",
            "parameter=cost",
        )
        change_markers = (
            "выраст",
            "увели",
            "уменьш",
            "сниз",
            "упад",
            "удво",
            "утро",
            "в 2",
            "в два",
            "в 3",
            "в три",
            "в 1.5",
            "×",
            "x2",
            "factor",
            "на ",
            "если ",
            "что если",
        )
        has_param = any(m in text for m in param_markers)
        has_change = any(m in text for m in change_markers)
        return has_param and has_change
