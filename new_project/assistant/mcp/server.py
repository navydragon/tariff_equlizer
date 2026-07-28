from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from asgiref.sync import sync_to_async
from mcp.server.fastmcp import FastMCP

from assistant.domain.tools.registry import call_tool, ensure_tools_loaded, list_tools

mcp = FastMCP("tariff-equalizer")
_BUILT = False


def _parse_overrides(overrides: str | dict | None) -> dict | None:
    if overrides is None or overrides == "":
        return None
    if isinstance(overrides, dict):
        return overrides
    try:
        parsed = json.loads(overrides)
    except json.JSONDecodeError:
        return None
    return parsed if isinstance(parsed, dict) else None


def _tool_result(result: dict[str, Any]) -> str:
    return json.dumps(result, ensure_ascii=False, indent=2)


async def _call_domain_tool(name: str, payload: dict[str, Any]) -> str:
    """Вызов Django/ORM domain tool из async MCP-контекста FastMCP."""
    result = await sync_to_async(call_tool, thread_sensitive=True)(name, payload)
    return _tool_result(result)


def build_mcp_server() -> FastMCP:
    global _BUILT
    ensure_tools_loaded()
    if _BUILT:
        return mcp
    _BUILT = True

    @mcp.tool()
    async def get_route_summary(scenario_id: int, route_id: int) -> str:
        """Краткая карточка маршрута и сценария (груз, холдинг, объём)."""
        return await _call_domain_tool(
            "get_route_summary",
            {"scenario_id": scenario_id, "route_id": route_id},
        )

    @mcp.tool()
    async def compute_route_analysis(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """Компактный расчёт «Экономика грузов»: KPI, эффекты, ключевые строки."""
        return await _call_domain_tool(
            "compute_route_analysis",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def get_kpi_summary(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """KPI по годам: транспорт, Ж/Д тариф, маржинальность, эластичность."""
        return await _call_domain_tool(
            "get_kpi_summary",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def get_effects_breakdown(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """Вклад базовых решений и отдельных тарифных правил по годам."""
        return await _call_domain_tool(
            "get_effects_breakdown",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def get_equalizer_state(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """Состояние эквалайзера и активные пользовательские overrides."""
        return await _call_domain_tool(
            "get_equalizer_state",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def get_margin_drivers(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """Драйверы маржинальности: цена, себестоимость, транспорт, тариф РЖД."""
        return await _call_domain_tool(
            "get_margin_drivers",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def get_tariff_coefficients(
        scenario_id: int,
        route_id: int,
        overrides_json: str = "",
    ) -> str:
        """Коэффициенты BTD (base) и отдельных правил по годам."""
        return await _call_domain_tool(
            "get_tariff_coefficients",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def simulate_parameter_factor(
        scenario_id: int,
        route_id: int,
        parameter: str,
        factor: float,
        overrides_json: str = "",
    ) -> str:
        """What-if: умножить параметр эквалайзера на factor и сравнить маржу."""
        return await _call_domain_tool(
            "simulate_parameter_factor",
            {
                "scenario_id": scenario_id,
                "route_id": route_id,
                "parameter": parameter,
                "factor": factor,
                "overrides": _parse_overrides(overrides_json),
            },
        )

    @mcp.tool()
    async def rank_routes(
        scenario_id: int,
        cargo_query: str,
        metric: str = "transport",
        limit: int = 5,
    ) -> str:
        """Топ маршрутов по грузу и метрике (transport/rzd/total_cost/price)."""
        return await _call_domain_tool(
            "rank_routes",
            {
                "scenario_id": scenario_id,
                "cargo_query": cargo_query,
                "metric": metric,
                "limit": limit,
            },
        )

    @mcp.tool()
    def list_domain_tools() -> str:
        """Список зарегистрированных domain tools."""
        tools = [
            {"name": t.name, "description": t.description, "read_only": t.read_only}
            for t in list_tools()
        ]
        return _tool_result({"success": True, "tools": tools})

    @mcp.resource("methodology://route-analysis")
    def route_analysis_methodology() -> str:
        """Краткая методика расчётов страницы «Экономика грузов» / эффектов."""
        docs = (
            Path(__file__).resolve().parents[2] / "docs" / "decision_effects_formulas.md"
        )
        if docs.exists():
            text = docs.read_text(encoding="utf-8")
            return text[:8000]
        return (
            "Документ методики не найден. "
            "Смотрите new_project/docs/decision_effects_formulas.md"
        )

    return mcp


def run_stdio() -> None:
    server = build_mcp_server()
    server.run(transport="stdio")
