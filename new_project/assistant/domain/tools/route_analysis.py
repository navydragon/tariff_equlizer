from __future__ import annotations

from typing import Any

from calculations.domain.services.tariff_load import TariffLoadService
from core.domain.route_analysis.dto import RouteAnalysisRequestDTO
from core.domain.route_analysis.services import RouteAnalysisService
from core.models import Route
from scenarios.models import Scenario

from assistant.domain.services.access import AssistantAccessHelper
from assistant.domain.tools.registry import ToolSpec, register_tool


def _error(errors: list[str]) -> dict[str, Any]:
    return {"success": False, "errors": errors}


def _ok(data: dict[str, Any]) -> dict[str, Any]:
    return {"success": True, **data}


def _resolve_context(
    *,
    scenario_id: int,
    route_id: int,
    user_id: int | None = None,
) -> tuple[Any, Any, list[str]]:
    user = None
    if user_id is not None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return None, None, ["Пользователь не найден"]

    ctx, errors = AssistantAccessHelper().require_route_analysis_context(
        scenario_id=int(scenario_id),
        route_id=int(route_id),
        user=user,
    )
    if errors or ctx is None:
        return None, None, errors
    return ctx.scenario, ctx.route, []


def _parse_overrides(raw: Any) -> dict | None:
    return RouteAnalysisRequestDTO.parse_overrides(raw)


def _compute_analysis(
    *,
    scenario,
    route,
    overrides: dict | None,
) -> Any:
    dto = RouteAnalysisRequestDTO(
        scenario_id=scenario.id,
        route_id=route.id,
        overrides=overrides,
    )
    return RouteAnalysisService().calculate(
        request_dto=dto,
        scenario=scenario,
        route=route,
    )


def _compact_from_response(response, *, include_rows_keys: list[str] | None = None) -> dict[str, Any]:
    payload = response.to_api_dict()
    rows = payload.get("rows") or []
    if include_rows_keys:
        keys = set(include_rows_keys)
        rows = [row for row in rows if row.get("key") in keys]
    else:
        # compact default: ключевые строки экономики
        default_keys = {
            "price_rub",
            "cost",
            "transport",
            "rzd",
            "oper",
            "per",
            "marginality",
        }
        rows = [row for row in rows if row.get("key") in default_keys]

    return {
        "scenario_id": payload.get("scenario_id"),
        "route_id": payload.get("route_id"),
        "route_code": payload.get("route_code"),
        "years": payload.get("years"),
        "rows": rows,
        "kpi": payload.get("kpi"),
        "effects": payload.get("effects"),
        "equalizer": payload.get("equalizer"),
    }


def get_route_summary(
    *,
    scenario_id: int,
    route_id: int,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    cargo = route.cargo
    shipper = route.shipper
    origin = route.origin_station
    destination = route.destination_station
    volume = route.transport_volume_tons

    return _ok(
        {
            "scenario": {
                "id": scenario.id,
                "name": scenario.name,
                "start_year": scenario.start_year,
                "end_year": scenario.end_year,
                "route_set": scenario.route_set.code if scenario.route_set_id else None,
            },
            "route": {
                "id": route.id,
                "route_code": route.route_code,
                "cargo_code": cargo.code if cargo else None,
                "cargo_name": cargo.name if cargo else None,
                "cargo_group": (
                    cargo.cargo_group.name
                    if cargo and cargo.cargo_group_id
                    else None
                ),
                "holding": shipper.holding if shipper else None,
                "shipper": shipper.name if shipper else None,
                "origin": (
                    (origin.full_name or origin.short_name) if origin else None
                ),
                "destination": (
                    (destination.full_name or destination.short_name)
                    if destination
                    else None
                ),
                "message_type": (
                    route.message_type.name if route.message_type_id else None
                ),
                "transport_volume_tons": format(volume, "f") if volume is not None else None,
            },
        },
    )


def compute_route_analysis(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    include_rows_keys: list[str] | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    parsed = _parse_overrides(overrides)
    response = _compute_analysis(scenario=scenario, route=route, overrides=parsed)
    compact = _compact_from_response(response, include_rows_keys=include_rows_keys)
    return _ok({"analysis": compact})


def get_kpi_summary(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    response = _compute_analysis(
        scenario=scenario,
        route=route,
        overrides=_parse_overrides(overrides),
    )
    return _ok(
        {
            "route_code": response.route_code,
            "years": response.years,
            "kpi": response.kpi.to_api_dict(),
        },
    )


def get_effects_breakdown(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    response = _compute_analysis(
        scenario=scenario,
        route=route,
        overrides=_parse_overrides(overrides),
    )
    return _ok(
        {
            "route_code": response.route_code,
            "years": response.years,
            "effects": response.effects.to_api_dict(),
        },
    )


def get_equalizer_state(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    parsed = _parse_overrides(overrides)
    response = _compute_analysis(scenario=scenario, route=route, overrides=parsed)
    return _ok(
        {
            "route_code": response.route_code,
            "years": response.years,
            "equalizer": response.equalizer.to_api_dict(),
            "active_overrides": {
                type_key: {str(year): format(value, "f") for year, value in year_map.items()}
                for type_key, year_map in (parsed or {}).items()
            },
        },
    )


MARGIN_ROW_KEYS = ("price_rub", "cost", "transport", "rzd", "oper", "per", "marginality")

WHAT_IF_PARAMETERS = frozenset(
    {"price_rub", "cost", "oper", "per", "base", "rules", "fx"},
)


def _row_values_by_year(response, key: str) -> dict[str, Any]:
    years = response.years
    for row in response.rows:
        if row.key != key:
            continue
        out: dict[str, Any] = {}
        for index, year in enumerate(years):
            raw = row.values[index] if index < len(row.values) else None
            out[str(year)] = raw
        return out
    return {}


def _extract_money_or_coef(raw: Any):
    from decimal import Decimal, InvalidOperation

    if raw is None:
        return None
    if isinstance(raw, dict):
        raw = raw.get("rub", raw.get("pct"))
    try:
        return Decimal(str(raw).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return None


def get_margin_drivers(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    response = _compute_analysis(
        scenario=scenario,
        route=route,
        overrides=_parse_overrides(overrides),
    )
    rows_by_key = {row.key: row for row in response.rows}
    drivers = []
    for key in MARGIN_ROW_KEYS:
        row = rows_by_key.get(key)
        if row is None:
            continue
        drivers.append(
            {
                "key": row.key,
                "label": row.label,
                "values": row.values,
                "format": row.format,
            },
        )
    return _ok(
        {
            "route_code": response.route_code,
            "years": response.years,
            "drivers": drivers,
        },
    )


def simulate_parameter_factor(
    *,
    scenario_id: int,
    route_id: int,
    parameter: str,
    factor: float | int | str,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    """
    What-if: умножить параметр эквалайзера на factor по всем годам и сравнить маржу.

    parameter: price_rub | cost | oper | per | base | rules | fx
    factor: например 2 = «вырастет в 2 раза».
    Overrides эквалайзера — абсолютные значения (руб./т или индекс), не множители.
    """
    from decimal import Decimal, InvalidOperation

    parameter = str(parameter or "").strip()
    if parameter not in WHAT_IF_PARAMETERS:
        return _error(
            [
                f"Недопустимый parameter: {parameter}. "
                f"Допустимо: {', '.join(sorted(WHAT_IF_PARAMETERS))}",
            ],
        )

    try:
        factor_dec = Decimal(str(factor).replace(",", "."))
    except (InvalidOperation, ValueError, TypeError):
        return _error(["Некорректный factor"])
    if factor_dec <= 0:
        return _error(["factor должен быть > 0"])

    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    base_overrides = _parse_overrides(overrides) or {}
    baseline = _compute_analysis(
        scenario=scenario,
        route=route,
        overrides=base_overrides or None,
    )

    equalizer_types = {item.key: item for item in baseline.equalizer.types}
    eq_type = equalizer_types.get(parameter)
    if eq_type is None:
        return _error([f"Параметр {parameter} недоступен для этого маршрута"])

    simulated_year_map: dict[int, Decimal] = {}
    baseline_param: dict[str, str] = {}
    for year_str, value_str in (eq_type.values or {}).items():
        year = int(year_str)
        base_val = _extract_money_or_coef(value_str)
        if base_val is None:
            continue
        new_val = (base_val * factor_dec).quantize(Decimal("0.0001"))
        simulated_year_map[year] = new_val
        baseline_param[year_str] = format(base_val, "f")

    if not simulated_year_map:
        return _error([f"Нет значений параметра {parameter} для умножения"])

    merged: dict[str, dict[int, Decimal]] = {
        key: dict(year_map) for key, year_map in base_overrides.items()
    }
    merged[parameter] = {
        **merged.get(parameter, {}),
        **simulated_year_map,
    }

    simulated = _compute_analysis(
        scenario=scenario,
        route=route,
        overrides=merged,
    )

    return _ok(
        {
            "route_code": baseline.route_code,
            "years": baseline.years,
            "parameter": parameter,
            "parameter_label": eq_type.label,
            "factor": format(factor_dec, "f"),
            "assumption": (
                f"{eq_type.label} умножена на {format(factor_dec, 'f')} "
                f"по всем годам (абсолютные overrides эквалайзера)."
            ),
            "baseline": {
                "parameter_by_year": baseline_param,
                "marginality": _row_values_by_year(baseline, "marginality"),
                "price_rub": _row_values_by_year(baseline, "price_rub"),
                "cost": _row_values_by_year(baseline, "cost"),
                "rzd": _row_values_by_year(baseline, "rzd"),
            },
            "simulated": {
                "parameter_by_year": {
                    str(y): format(v, "f") for y, v in simulated_year_map.items()
                },
                "marginality": _row_values_by_year(simulated, "marginality"),
                "price_rub": _row_values_by_year(simulated, "price_rub"),
                "cost": _row_values_by_year(simulated, "cost"),
                "rzd": _row_values_by_year(simulated, "rzd"),
            },
            # Для UI: применить к эквалайзеру (абсолютные значения по годам).
            "ui_overrides": {
                **{
                    type_key: {
                        str(year): format(value, "f")
                        for year, value in year_map.items()
                    }
                    for type_key, year_map in base_overrides.items()
                },
                parameter: {
                    str(y): format(v, "f") for y, v in simulated_year_map.items()
                },
            },
            "ui_focus_equalizer_type": parameter,
            "note": (
                "Отвечай только цифрами из baseline/simulated. "
                "Не экстраполируй и не округляй произвольно."
            ),
        },
    )


def get_tariff_coefficients(
    *,
    scenario_id: int,
    route_id: int,
    overrides: dict | None = None,
    user_id: int | None = None,
) -> dict[str, Any]:
    scenario, route, errors = _resolve_context(
        scenario_id=scenario_id,
        route_id=route_id,
        user_id=user_id,
    )
    if errors:
        return _error(errors)

    parsed = _parse_overrides(overrides) or {}
    tariff = TariffLoadService().calculate_route(
        scenario=scenario,
        route=route,
        base_coef_overrides=parsed.get("base"),
        rules_coef_overrides=parsed.get("rules"),
    )
    return _ok(
        {
            "route_code": tariff.route_code,
            "years": tariff.years,
            "base_coefficient_by_year": {
                str(y): format(v, "f") for y, v in tariff.base_coefficient_by_year.items()
            },
            "rules_coefficient_by_year": {
                str(y): format(v, "f") for y, v in tariff.rules_coefficient_by_year.items()
            },
            "rzd_by_year": {
                str(y): format(v, "f") for y, v in tariff.rzd_by_year.items()
            },
        },
    )


_COMMON_CONTEXT_PROPS: dict[str, Any] = {
    "scenario_id": {"type": "integer", "description": "ID сценария"},
    "route_id": {"type": "integer", "description": "ID маршрута"},
    "user_id": {
        "type": "integer",
        "description": "ID пользователя для ACL (опционально; в UI передаётся автоматически)",
    },
}

_OVERRIDES_PROP: dict[str, Any] = {
    "overrides": {
        "type": "object",
        "description": "Overrides эквалайзера: cost/oper/per/price_rub/fx/base/rules → {year: value}",
        "additionalProperties": True,
    },
}

_RANK_METRICS: dict[str, str] = {
    "transport": "transport_total_cost_per_ton",
    "rzd": "rzd_cost_total_per_ton",
    "total_cost": "total_cost_per_ton",
    "price": "market_price_per_ton",
}


def _station_label(station) -> str | None:
    if station is None:
        return None
    return station.full_name or station.short_name or str(station.esr_code)


def rank_routes(
    *,
    scenario_id: int,
    cargo_query: str,
    metric: str = "transport",
    limit: int = 5,
    user_id: int | None = None,
) -> dict[str, Any]:
    """Топ маршрутов сценария по метрике (цена / транспорт / тариф / полная себестоимость)."""
    from django.db.models import F, Q

    metric_key = (metric or "transport").strip().lower()
    field = _RANK_METRICS.get(metric_key)
    if field is None:
        allowed = ", ".join(sorted(_RANK_METRICS))
        return _error([f"Неизвестная metric «{metric}». Допустимо: {allowed}"])

    query = (cargo_query or "").strip()
    if not query:
        return _error(["Укажите cargo_query, например «уголь»"])

    try:
        limit_n = max(1, min(int(limit), 50))
    except (TypeError, ValueError):
        return _error(["limit должен быть целым числом"])

    user = None
    if user_id is not None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        try:
            user = User.objects.get(pk=user_id)
        except User.DoesNotExist:
            return _error(["Пользователь не найден"])

    try:
        scenario = Scenario.objects.select_related("route_set").get(pk=int(scenario_id))
    except Scenario.DoesNotExist:
        return _error(["Сценарий не найден"])

    if user is not None:
        from core.domain.services.app_settings import AppSettingsService

        if not AppSettingsService().can_read_scenario(
            author_id=scenario.author_id,
            user_id=user.id,
        ):
            return _error(["Сценарий не найден"])

    if not scenario.route_set_id:
        return _error(["У сценария не задан набор маршрутов"])

    qs = (
        Route.objects.filter(route_set_id=scenario.route_set_id)
        .filter(
            Q(cargo__name__icontains=query)
            | Q(cargo__cargo_group__name__istartswith=query)
            | Q(cargo__code__icontains=query),
        )
        .exclude(**{f"{field}__isnull": True})
        .select_related(
            "cargo",
            "cargo__cargo_group",
            "shipper",
            "origin_station",
            "destination_station",
        )
        .order_by(F(field).desc(), "id")[:limit_n]
    )

    items: list[dict[str, Any]] = []
    for route in qs:
        cargo = route.cargo
        shipper = route.shipper
        value = getattr(route, field)
        items.append(
            {
                "route_id": route.id,
                "route_code": route.route_code,
                "metric": metric_key,
                "metric_field": field,
                "metric_value": format(value, "f") if value is not None else None,
                "cargo_name": cargo.name if cargo else None,
                "cargo_group": (
                    cargo.cargo_group.name
                    if cargo and cargo.cargo_group_id
                    else None
                ),
                "holding": shipper.holding if shipper else None,
                "origin": _station_label(route.origin_station),
                "destination": _station_label(route.destination_station),
                "transport_total_cost_per_ton": (
                    format(route.transport_total_cost_per_ton, "f")
                    if route.transport_total_cost_per_ton is not None
                    else None
                ),
                "rzd_cost_total_per_ton": (
                    format(route.rzd_cost_total_per_ton, "f")
                    if route.rzd_cost_total_per_ton is not None
                    else None
                ),
                "market_price_per_ton": (
                    format(route.market_price_per_ton, "f")
                    if route.market_price_per_ton is not None
                    else None
                ),
                "total_cost_per_ton": (
                    format(route.total_cost_per_ton, "f")
                    if route.total_cost_per_ton is not None
                    else None
                ),
            },
        )

    return _ok(
        {
            "scenario_id": scenario.id,
            "cargo_query": query,
            "metric": metric_key,
            "metric_field": field,
            "count": len(items),
            "routes": items,
        },
    )


def _register_all() -> None:
    register_tool(
        ToolSpec(
            name="get_route_summary",
            description="Краткая карточка маршрута и сценария (груз, холдинг, объём).",
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_route_summary,
        ),
    )
    register_tool(
        ToolSpec(
            name="compute_route_analysis",
            description=(
                "Компактный расчёт «Экономика грузов»: KPI, эффекты, ключевые строки таблицы."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_COMMON_CONTEXT_PROPS,
                    **_OVERRIDES_PROP,
                    "include_rows_keys": {
                        "type": "array",
                        "items": {"type": "string"},
                        "description": "Опциональный список ключей строк таблицы",
                    },
                },
                "required": ["scenario_id", "route_id"],
            },
            handler=compute_route_analysis,
        ),
    )
    register_tool(
        ToolSpec(
            name="get_kpi_summary",
            description="KPI по годам: транспорт, Ж/Д тариф, маржинальность, эластичность.",
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS, **_OVERRIDES_PROP},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_kpi_summary,
        ),
    )
    register_tool(
        ToolSpec(
            name="get_effects_breakdown",
            description="Вклад базовых решений и отдельных тарифных правил по годам.",
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS, **_OVERRIDES_PROP},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_effects_breakdown,
        ),
    )
    register_tool(
        ToolSpec(
            name="get_equalizer_state",
            description="Состояние эквалайзера и активные пользовательские overrides.",
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS, **_OVERRIDES_PROP},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_equalizer_state,
        ),
    )
    register_tool(
        ToolSpec(
            name="get_margin_drivers",
            description=(
                "Драйверы маржинальности: цена, себестоимость, транспорт, тариф РЖД по годам."
            ),
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS, **_OVERRIDES_PROP},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_margin_drivers,
        ),
    )
    register_tool(
        ToolSpec(
            name="get_tariff_coefficients",
            description="Коэффициенты BTD (base) и отдельных правил (rules) по годам, тариф РЖД.",
            parameters={
                "type": "object",
                "properties": {**_COMMON_CONTEXT_PROPS, **_OVERRIDES_PROP},
                "required": ["scenario_id", "route_id"],
            },
            handler=get_tariff_coefficients,
        ),
    )
    register_tool(
        ToolSpec(
            name="simulate_parameter_factor",
            description=(
                "What-if сценарий: умножить параметр эквалайзера (price_rub/cost/…) "
                "на factor по всем годам и сравнить маржинальность baseline vs simulated. "
                "Обязателен для вопросов «что если цена вырастет в N раз»."
            ),
            parameters={
                "type": "object",
                "properties": {
                    **_COMMON_CONTEXT_PROPS,
                    **_OVERRIDES_PROP,
                    "parameter": {
                        "type": "string",
                        "description": "price_rub | cost | oper | per | base | rules | fx",
                    },
                    "factor": {
                        "type": "number",
                        "description": "Множитель, например 2.0",
                    },
                },
                "required": ["scenario_id", "route_id", "parameter", "factor"],
            },
            handler=simulate_parameter_factor,
        ),
    )
    register_tool(
        ToolSpec(
            name="rank_routes",
            description=(
                "Топ маршрутов сценария по грузу и метрике стоимости. "
                "Для вопросов вроде «самый дорогой маршрут по углю»: "
                "cargo_query=уголь, metric=transport|rzd|total_cost|price."
            ),
            parameters={
                "type": "object",
                "properties": {
                    "scenario_id": {
                        "type": "integer",
                        "description": "ID сценария",
                    },
                    "cargo_query": {
                        "type": "string",
                        "description": "Подстрока груза/группы/кода, например «уголь»",
                    },
                    "metric": {
                        "type": "string",
                        "description": (
                            "transport (транспорт) | rzd (тариф РЖД) | "
                            "total_cost (полная себестоимость) | price (рыночная цена)"
                        ),
                        "default": "transport",
                    },
                    "limit": {
                        "type": "integer",
                        "description": "Сколько маршрутов вернуть (1–50)",
                        "default": 5,
                    },
                },
                "required": ["scenario_id", "cargo_query"],
            },
            handler=rank_routes,
        ),
    )


_register_all()
