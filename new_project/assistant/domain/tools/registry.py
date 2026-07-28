from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable


ToolHandler = Callable[..., dict[str, Any]]


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    parameters: dict[str, Any]
    handler: ToolHandler
    read_only: bool = True


_REGISTRY: dict[str, ToolSpec] = {}


def register_tool(spec: ToolSpec) -> ToolSpec:
    if spec.name in _REGISTRY:
        raise ValueError(f"Tool already registered: {spec.name}")
    _REGISTRY[spec.name] = spec
    return spec


def get_tool(name: str) -> ToolSpec | None:
    return _REGISTRY.get(name)


def list_tools() -> list[ToolSpec]:
    return list(_REGISTRY.values())


def call_tool(name: str, arguments: dict[str, Any] | None = None) -> dict[str, Any]:
    spec = get_tool(name)
    if spec is None:
        return {"success": False, "errors": [f"Неизвестный tool: {name}"]}
    args = arguments or {}
    try:
        return spec.handler(**args)
    except TypeError as exc:
        return {"success": False, "errors": [f"Некорректные аргументы для {name}: {exc}"]}
    except Exception as exc:  # noqa: BLE001 — surface to LLM/UI as tool error
        return {"success": False, "errors": [str(exc)]}


def openai_tools_schema() -> list[dict[str, Any]]:
    """Схема tools в формате OpenAI chat completions."""
    result: list[dict[str, Any]] = []
    for spec in list_tools():
        result.append(
            {
                "type": "function",
                "function": {
                    "name": spec.name,
                    "description": spec.description,
                    "parameters": spec.parameters,
                },
            },
        )
    return result


def ensure_tools_loaded() -> None:
    """Импортирует модули с регистрацией tools (идемпотентно)."""
    if _REGISTRY:
        return
    from assistant.domain.tools import route_analysis as _route_analysis  # noqa: F401
