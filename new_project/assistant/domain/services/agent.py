from __future__ import annotations

import logging
from typing import Any

from pydantic_ai import Agent, RunContext
from pydantic_ai.models.openai import OpenAIChatModel
from pydantic_ai.providers.openai import OpenAIProvider

from assistant.domain.services.deps import AssistantDeps
from assistant.domain.tools.registry import call_tool, ensure_tools_loaded

logger = logging.getLogger(__name__)

AGENT_INSTRUCTIONS = """\
Ты ассистент страницы «Экономика грузов» тарифного эквалайзера.

Правила:
1. Отвечай кратко на русском языке.
2. Любые цифры бери ТОЛЬКО из результатов tools. Не выдумывай и не «прикидывай».
3. Для вопросов «что если» про изменение параметра с явной величиной
   (цена ×2, себестоимость вырастет в 1.5 раза и т.п.) вызывай simulate_parameter_factor:
   - цена → parameter=price_rub
   - себестоимость → parameter=cost
   - операторы → parameter=oper
   - перевалка → parameter=per
   - тариф / индексация → parameter=base
   - тарифные решения / правила → parameter=rules
4. Если параметр выбран, но величина изменения НЕ указана — НЕ вызывай tools.
   Спроси: «во сколько раз?» и предложи варианты словами: «в 1.5 раза», «в 2 раза», «в 3 раза»
   (не нумеруй их как 1/2/3 — только словами, чтобы не путать с выбором меню).
5. Если вопрос размытый — не вызывай tools, попроси уточнить параметр словами
   («цена», «себестоимость», «тариф»), без нумерованных списков 1/2/3.
6. Короткий ответ пользователя вроде «3» / «2» после меню вариантов — это ВЫБОР ПУНКТА,
   а не множитель factor. Не интерпретируй его как factor=3.
7. Не подставляй scenario_id/route_id вручную — они уже в контексте tools.
8. Не предлагай менять сценарий или правила без явного запроса.
"""


def _track(ctx: RunContext[AssistantDeps], name: str) -> None:
    ctx.deps.tools_used.append(name)


def get_route_summary(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """Краткая карточка маршрута и сценария (груз, холдинг, объём)."""
    _track(ctx, "get_route_summary")
    return call_tool("get_route_summary", ctx.deps.tool_kwargs())


def compute_route_analysis(
    ctx: RunContext[AssistantDeps],
    include_rows_keys: list[str] | None = None,
) -> dict[str, Any]:
    """Компактный расчёт экономики: KPI, эффекты, ключевые строки таблицы."""
    _track(ctx, "compute_route_analysis")
    kwargs = ctx.deps.tool_kwargs()
    if include_rows_keys:
        kwargs["include_rows_keys"] = include_rows_keys
    return call_tool("compute_route_analysis", kwargs)


def get_kpi_summary(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """KPI по годам: транспорт, Ж/Д тариф, маржинальность, эластичность."""
    _track(ctx, "get_kpi_summary")
    return call_tool("get_kpi_summary", ctx.deps.tool_kwargs())


def get_effects_breakdown(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """Вклад базовых решений и отдельных тарифных правил по годам."""
    _track(ctx, "get_effects_breakdown")
    return call_tool("get_effects_breakdown", ctx.deps.tool_kwargs())


def get_equalizer_state(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """Состояние эквалайзера и активные пользовательские overrides."""
    _track(ctx, "get_equalizer_state")
    return call_tool("get_equalizer_state", ctx.deps.tool_kwargs())


def get_margin_drivers(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """Драйверы маржинальности: цена, себестоимость, транспорт, тариф РЖД."""
    _track(ctx, "get_margin_drivers")
    return call_tool("get_margin_drivers", ctx.deps.tool_kwargs())


def get_tariff_coefficients(ctx: RunContext[AssistantDeps]) -> dict[str, Any]:
    """Коэффициенты BTD (base) и отдельных правил (rules) по годам."""
    _track(ctx, "get_tariff_coefficients")
    return call_tool("get_tariff_coefficients", ctx.deps.tool_kwargs())


def simulate_parameter_factor(
    ctx: RunContext[AssistantDeps],
    parameter: str,
    factor: float,
) -> dict[str, Any]:
    """What-if: умножить параметр эквалайзера на factor и сравнить маржу.

    Args:
        parameter: price_rub | cost | oper | per | base | rules | fx
        factor: множитель, например 2.0 для «вырастет в 2 раза»
    """
    _track(ctx, "simulate_parameter_factor")
    kwargs = ctx.deps.tool_kwargs()
    kwargs["parameter"] = parameter
    kwargs["factor"] = factor
    result = call_tool("simulate_parameter_factor", kwargs)
    if result.get("success") and result.get("ui_overrides"):
        ctx.deps.ui_action = {
            "apply_equalizer_overrides": result["ui_overrides"],
            "focus_equalizer_type": result.get("ui_focus_equalizer_type") or parameter,
        }
    return result


def build_route_analysis_agent(*, model_name: str, api_key: str, base_url: str) -> Agent[AssistantDeps, str]:
    """Создаёт Pydantic AI Agent с domain tools."""
    ensure_tools_loaded()
    model = OpenAIChatModel(
        model_name,
        provider=OpenAIProvider(base_url=base_url, api_key=api_key),
    )
    return Agent(
        model,
        deps_type=AssistantDeps,
        output_type=str,
        instructions=AGENT_INSTRUCTIONS,
        tools=[
            get_route_summary,
            compute_route_analysis,
            get_kpi_summary,
            get_effects_breakdown,
            get_equalizer_state,
            get_margin_drivers,
            get_tariff_coefficients,
            simulate_parameter_factor,
        ],
    )
