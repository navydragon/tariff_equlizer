from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


PRESET_IDS = frozenset(
    {
        "route_summary",
        "explain_kpi",
        "explain_effects",
        "explain_margin",
        "explain_equalizer",
    },
)

PRESET_LABELS: dict[str, str] = {
    "route_summary": "Кратко о маршруте",
    "explain_kpi": "KPI по годам",
    "explain_effects": "Вклад решений и правил",
    "explain_margin": "Драйверы маржинальности",
    "explain_equalizer": "Текущий эквалайзер",
}


@dataclass(frozen=True)
class CitationDTO:
    section: str
    year: int | None = None
    detail: str | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {"section": self.section}
        if self.year is not None:
            payload["year"] = self.year
        if self.detail:
            payload["detail"] = self.detail
        return payload


@dataclass(frozen=True)
class ChatRequestDTO:
    page: str
    message: str
    preset: str | None
    scenario_id: int | None
    route_id: int | None
    overrides: dict[str, Any] | None
    snapshot: dict[str, Any] | None
    history: list[dict[str, str]]

    def validate(self) -> list[str]:
        errors: list[str] = []
        if self.page != "route_analysis":
            errors.append("Поддерживается только page=route_analysis")
        if self.preset is not None and self.preset not in PRESET_IDS:
            errors.append(f"Неизвестный preset: {self.preset}")
        if not self.preset and not (self.message or "").strip():
            errors.append("Укажите message или preset")
        if self.scenario_id is None or self.scenario_id <= 0:
            errors.append("Некорректный scenario_id")
        if self.route_id is None or self.route_id <= 0:
            errors.append("Некорректный route_id")
        return errors

    @classmethod
    def from_payload(cls, data: dict[str, Any]) -> ChatRequestDTO:
        context = data.get("context") or {}
        if not isinstance(context, dict):
            context = {}

        scenario_id = context.get("scenario_id", data.get("scenario_id"))
        route_id = context.get("route_id", data.get("route_id"))
        try:
            scenario_id = int(scenario_id) if scenario_id is not None else None
        except (TypeError, ValueError):
            scenario_id = None
        try:
            route_id = int(route_id) if route_id is not None else None
        except (TypeError, ValueError):
            route_id = None

        history_raw = data.get("history") or []
        history: list[dict[str, str]] = []
        if isinstance(history_raw, list):
            for item in history_raw[-10:]:
                if not isinstance(item, dict):
                    continue
                role = str(item.get("role") or "").strip()
                content = str(item.get("content") or "").strip()
                if role in {"user", "assistant"} and content:
                    history.append({"role": role, "content": content})

        overrides = context.get("overrides")
        if overrides is not None and not isinstance(overrides, dict):
            overrides = None

        snapshot = context.get("snapshot")
        if snapshot is not None and not isinstance(snapshot, dict):
            snapshot = None

        preset = data.get("preset")
        if preset is not None:
            preset = str(preset).strip() or None

        return cls(
            page=str(data.get("page") or "").strip(),
            message=str(data.get("message") or "").strip(),
            preset=preset,
            scenario_id=scenario_id,
            route_id=route_id,
            overrides=overrides,
            snapshot=snapshot,
            history=history,
        )


@dataclass(frozen=True)
class ChatResponseDTO:
    mode: str
    answer: str
    citations: list[CitationDTO] = field(default_factory=list)
    tools_used: list[str] = field(default_factory=list)
    ui_action: dict[str, Any] | None = None

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "mode": self.mode,
            "answer": self.answer,
            "citations": [c.to_api_dict() for c in self.citations],
            "tools_used": list(self.tools_used),
        }
        if self.ui_action:
            payload["ui_action"] = self.ui_action
        return payload
