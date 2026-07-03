from __future__ import annotations

import logging
from typing import Any

_TOP_N = 5


def log_warm_timings(
    logger: logging.Logger,
    *,
    label: str,
    phases: dict[str, int],
    detail: dict[str, int | str] | None = None,
    **context: Any,
) -> None:
    """Логирует wall-clock фазы пересчёта и самые медленные подэтапы."""
    total_ms = phases.get("total_ms")
    if total_ms is None:
        total_ms = sum(phases.values())

    top_phases = sorted(
        (
            (name, value)
            for name, value in phases.items()
            if name != "total_ms" and isinstance(value, int)
        ),
        key=lambda item: item[1],
        reverse=True,
    )[:_TOP_N]
    phase_str = ", ".join(f"{name}={value}ms" for name, value in top_phases)
    context_str = " ".join(
        f"{name}={value}" for name, value in context.items()
    )

    parts = [f"Scenario rebuild {label} total={total_ms}ms | top: {phase_str}"]
    if context_str:
        parts.append(context_str)

    if detail:
        numeric_detail = {
            name: value
            for name, value in detail.items()
            if isinstance(value, int) and not name.startswith("fallout_")
        }
        top_detail = sorted(
            numeric_detail.items(),
            key=lambda item: item[1],
            reverse=True,
        )[:_TOP_N]
        if top_detail:
            detail_str = ", ".join(
                f"{name}={value}ms" for name, value in top_detail
            )
            parts.append(f"| detail: {detail_str}")

    logger.info(" ".join(parts))
