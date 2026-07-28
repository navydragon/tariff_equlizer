from __future__ import annotations

import logging
import time
from collections import defaultdict
from typing import Any

from django.conf import settings

from assistant.domain.dto.chat import (
    ChatRequestDTO,
    ChatResponseDTO,
    CitationDTO,
)
from assistant.domain.services.access import AssistantAccessHelper
from assistant.domain.services import formatters
from assistant.domain.services.llm import AssistantLlmClient
from assistant.domain.tools.registry import call_tool, ensure_tools_loaded

logger = logging.getLogger(__name__)

_RATE_BUCKETS: dict[int, list[float]] = defaultdict(list)


class AssistantChatService:
    def __init__(
        self,
        access: AssistantAccessHelper | None = None,
        llm: AssistantLlmClient | None = None,
    ) -> None:
        self._access = access or AssistantAccessHelper()
        self._llm = llm or AssistantLlmClient()
        ensure_tools_loaded()

    def chat(self, *, user, request_dto: ChatRequestDTO) -> tuple[ChatResponseDTO | None, list[str]]:
        errors = request_dto.validate()
        if errors:
            return None, errors

        rate_errors = self._check_rate_limit(user_id=user.id)
        if rate_errors:
            return None, rate_errors

        ctx, access_errors = self._access.require_route_analysis_context(
            scenario_id=request_dto.scenario_id,  # type: ignore[arg-type]
            route_id=request_dto.route_id,  # type: ignore[arg-type]
            user=user,
        )
        if access_errors or ctx is None:
            return None, access_errors

        tool_kwargs: dict[str, Any] = {
            "scenario_id": request_dto.scenario_id,
            "route_id": request_dto.route_id,
            "user_id": user.id,
        }
        if request_dto.overrides:
            tool_kwargs["overrides"] = request_dto.overrides

        if request_dto.preset:
            response, preset_errors = self._handle_preset(
                preset=request_dto.preset,
                tool_kwargs=tool_kwargs,
            )
            if preset_errors:
                return None, preset_errors
            logger.info(
                "assistant chat mode=preset user_id=%s scenario_id=%s route_id=%s "
                "preset=%s tools=%s",
                user.id,
                request_dto.scenario_id,
                request_dto.route_id,
                request_dto.preset,
                response.tools_used if response else [],
            )
            return response, []

        if not self._llm.is_configured():
            return None, [formatters.list_preset_help()]

        llm_context = {
            "scenario_id": request_dto.scenario_id,
            "route_id": request_dto.route_id,
            "user_id": user.id,
            "overrides": request_dto.overrides or {},
            "route_code": ctx.route.route_code,
            "scenario_name": ctx.scenario.name,
        }
        try:
            answer, tools_used, ui_action = self._llm.run_with_tools(
                message=request_dto.message,
                history=request_dto.history,
                context=llm_context,
            )
        except RuntimeError as exc:
            return None, [str(exc)]

        logger.info(
            "assistant chat mode=llm user_id=%s scenario_id=%s route_id=%s tools=%s ui=%s",
            user.id,
            request_dto.scenario_id,
            request_dto.route_id,
            tools_used,
            bool(ui_action),
        )
        return (
            ChatResponseDTO(
                mode="llm",
                answer=answer,
                citations=[CitationDTO(section="llm")],
                tools_used=tools_used,
                ui_action=ui_action,
            ),
            [],
        )

    def _handle_preset(
        self,
        *,
        preset: str,
        tool_kwargs: dict[str, Any],
    ) -> tuple[ChatResponseDTO | None, list[str]]:
        if preset == "route_summary":
            result = call_tool("get_route_summary", tool_kwargs)
            tools_used = ["get_route_summary"]
            if not result.get("success"):
                return None, result.get("errors") or ["Ошибка tool"]
            answer, citations = formatters.format_route_summary(result)
        elif preset == "explain_kpi":
            result = call_tool("get_kpi_summary", tool_kwargs)
            tools_used = ["get_kpi_summary"]
            if not result.get("success"):
                return None, result.get("errors") or ["Ошибка tool"]
            answer, citations = formatters.format_kpi(result)
        elif preset == "explain_effects":
            result = call_tool("get_effects_breakdown", tool_kwargs)
            tools_used = ["get_effects_breakdown"]
            if not result.get("success"):
                return None, result.get("errors") or ["Ошибка tool"]
            answer, citations = formatters.format_effects(result)
        elif preset == "explain_margin":
            result = call_tool("get_margin_drivers", tool_kwargs)
            tools_used = ["get_margin_drivers"]
            if not result.get("success"):
                return None, result.get("errors") or ["Ошибка tool"]
            answer, citations = formatters.format_margin(result)
        elif preset == "explain_equalizer":
            result = call_tool("get_equalizer_state", tool_kwargs)
            tools_used = ["get_equalizer_state"]
            if not result.get("success"):
                return None, result.get("errors") or ["Ошибка tool"]
            answer, citations = formatters.format_equalizer(result)
        else:
            return None, [f"Неизвестный preset: {preset}"]

        return (
            ChatResponseDTO(
                mode="preset",
                answer=answer,
                citations=citations,
                tools_used=tools_used,
            ),
            [],
        )

    def _check_rate_limit(self, *, user_id: int) -> list[str]:
        limit = int(getattr(settings, "ASSISTANT_CHAT_RATE_LIMIT_PER_MIN", 30))
        now = time.monotonic()
        window_start = now - 60.0
        bucket = _RATE_BUCKETS[user_id]
        _RATE_BUCKETS[user_id] = [ts for ts in bucket if ts >= window_start]
        if len(_RATE_BUCKETS[user_id]) >= limit:
            return ["Слишком много запросов. Подождите минуту."]
        _RATE_BUCKETS[user_id].append(now)
        return []
