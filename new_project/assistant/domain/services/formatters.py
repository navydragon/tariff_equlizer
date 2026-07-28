from __future__ import annotations

from typing import Any

from assistant.domain.dto.chat import PRESET_LABELS, CitationDTO


def _fmt_metric(metric: dict[str, Any] | None) -> str:
    if not metric:
        return "—"
    parts: list[str] = []
    if metric.get("rub") is not None:
        parts.append(f"{metric['rub']} руб.")
    if metric.get("pct") is not None:
        parts.append(f"{metric['pct']} %")
    return ", ".join(parts) if parts else "—"


def format_route_summary(data: dict[str, Any]) -> tuple[str, list[CitationDTO]]:
    scenario = data.get("scenario") or {}
    route = data.get("route") or {}
    lines = [
        f"**Сценарий:** {scenario.get('name')} "
        f"({scenario.get('start_year')}–{scenario.get('end_year')})",
        f"**Маршрут:** {route.get('route_code') or '—'}",
        f"**Груз:** {route.get('cargo_code')} — {route.get('cargo_name') or '—'}",
        f"**Группа груза:** {route.get('cargo_group') or '—'}",
        f"**Холдинг:** {route.get('holding') or '—'}",
        f"**Отправитель:** {route.get('shipper') or '—'}",
        f"**Направление:** {route.get('origin') or '—'} → {route.get('destination') or '—'}",
        f"**Вид сообщения:** {route.get('message_type') or '—'}",
        f"**Объём, т:** {route.get('transport_volume_tons') or '—'}",
    ]
    return "\n".join(lines), [CitationDTO(section="route_summary")]


def format_kpi(data: dict[str, Any]) -> tuple[str, list[CitationDTO]]:
    kpi = (data.get("kpi") or {}).get("by_year") or []
    lines = [
        f"**KPI маршрута {data.get('route_code') or ''}**",
        "",
    ]
    citations: list[CitationDTO] = []
    for year_block in kpi:
        year = year_block.get("year")
        lines.append(f"### {year}")
        lines.append(f"- Транспорт: {_fmt_metric(year_block.get('transport'))}")
        lines.append(f"- Ж/Д тариф: {_fmt_metric(year_block.get('rzd'))}")
        lines.append(f"- Маржинальность: {_fmt_metric(year_block.get('marginality'))}")
        lines.append(f"- Доля объёма: {_fmt_metric(year_block.get('volume_share'))}")
        lines.append(f"- Эластичность: {_fmt_metric(year_block.get('elasticity'))}")
        lines.append("")
        if year is not None:
            citations.append(CitationDTO(section="kpi", year=int(year)))
    if not kpi:
        lines.append("Нет данных KPI для выбранного маршрута.")
    return "\n".join(lines).strip(), citations


def format_effects(data: dict[str, Any]) -> tuple[str, list[CitationDTO]]:
    effects = (data.get("effects") or {}).get("rows") or []
    lines = [
        f"**Эффекты решений — {data.get('route_code') or ''}**",
        "",
    ]
    citations: list[CitationDTO] = [CitationDTO(section="effects")]
    for row in effects:
        label = row.get("label") or row.get("key")
        lines.append(f"### {label}")
        values = row.get("values") or {}
        for year in sorted(values.keys(), key=lambda y: int(y)):
            cell = values[year] or {}
            rub = cell.get("rub", "—")
            pct = cell.get("pct", "—")
            lines.append(f"- {year}: {rub} руб. ({pct} %)")
        lines.append("")
    if not effects:
        lines.append("Нет строк эффектов.")
    return "\n".join(lines).strip(), citations


def format_margin(data: dict[str, Any]) -> tuple[str, list[CitationDTO]]:
    years = data.get("years") or []
    drivers = data.get("drivers") or []
    lines = [
        f"**Драйверы маржинальности — {data.get('route_code') or ''}**",
        f"Годы: {', '.join(str(y) for y in years)}",
        "",
    ]
    for driver in drivers:
        label = driver.get("label") or driver.get("key")
        values = driver.get("values") or []
        pretty: list[str] = []
        for idx, year in enumerate(years):
            raw = values[idx] if idx < len(values) else None
            if isinstance(raw, dict):
                pretty.append(f"{year}: {raw.get('rub', '—')} руб. ({raw.get('pct', '—')} %)")
            else:
                pretty.append(f"{year}: {raw if raw is not None else '—'}")
        lines.append(f"**{label}**")
        lines.extend(f"- {item}" for item in pretty)
        lines.append("")
    return "\n".join(lines).strip(), [CitationDTO(section="margin")]


def format_equalizer(data: dict[str, Any]) -> tuple[str, list[CitationDTO]]:
    equalizer = data.get("equalizer") or {}
    types = equalizer.get("types") or []
    overrides = data.get("active_overrides") or {}
    lines = [
        f"**Эквалайзер — {data.get('route_code') or ''}**",
        "",
    ]
    if overrides:
        lines.append("**Активные overrides:**")
        for type_key, year_map in overrides.items():
            for year, value in year_map.items():
                lines.append(f"- {type_key} / {year}: {value}")
        lines.append("")
    else:
        lines.append("Пользовательские overrides не заданы (базовые значения сценария).")
        lines.append("")

    lines.append("**Типы ползунков:**")
    for item in types:
        if not item.get("visible", True):
            continue
        label = item.get("label") or item.get("key")
        unit = item.get("unit") or ""
        notice = item.get("notice") or ""
        editable = "да" if item.get("editable", True) else "нет"
        lines.append(f"- **{label}** ({item.get('key')}), ед.: {unit}, редактируемый: {editable}")
        if notice:
            lines.append(f"  _{notice}_")
        values = item.get("values") or {}
        if values:
            preview = ", ".join(f"{y}={v}" for y, v in list(values.items())[:6])
            lines.append(f"  значения: {preview}")
    return "\n".join(lines).strip(), [CitationDTO(section="equalizer")]


def format_tool_error(errors: list[str]) -> str:
    return "Не удалось получить данные: " + "; ".join(errors)


def list_preset_help() -> str:
    items = "\n".join(f"- `{key}` — {label}" for key, label in PRESET_LABELS.items())
    return (
        "Свободный текстовый диалог сейчас недоступен "
        "(LLM выключен). Используйте быстрые вопросы:\n\n"
        f"{items}"
    )
