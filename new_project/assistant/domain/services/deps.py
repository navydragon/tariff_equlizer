from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


@dataclass
class AssistantDeps:
    """Зависимости Pydantic AI agent: контекст страницы «Экономика грузов»."""

    scenario_id: int
    route_id: int
    user_id: int
    overrides: dict[str, Any] = field(default_factory=dict)
    tools_used: list[str] = field(default_factory=list)
    # UI side-effect после what-if (equalizer overrides)
    ui_action: dict[str, Any] | None = None

    def tool_kwargs(self, *, overrides: dict[str, Any] | None = None) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "route_id": self.route_id,
            "user_id": self.user_id,
            "overrides": overrides if overrides is not None else (self.overrides or {}),
        }
