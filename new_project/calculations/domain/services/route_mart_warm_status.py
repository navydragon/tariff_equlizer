from __future__ import annotations

import time
from dataclasses import dataclass
from typing import Any, Literal

from django.core.cache import cache

from calculations.domain.services.route_mart_store import (
    REFS_VERSION_CACHE_SECONDS,
    ensure_compute_sidecars,
    mart_meta_path,
    resolve_mart_parquet_path,
)

MartWarmPhase = Literal["queued", "building", "done", "error"]

ROUTE_MART_WARM_STATUS_PREFIX = "route_mart_warm"


@dataclass
class RouteMartWarmStatus:
    route_set_id: int
    refs_version: str
    phase: MartWarmPhase
    started_at: float = 0.0
    updated_at: float = 0.0
    error: str | None = None


def route_mart_warm_status_cache_key(*, route_set_id: int) -> str:
    return f"{ROUTE_MART_WARM_STATUS_PREFIX}:{route_set_id}"


def is_route_mart_ready(*, route_set_id: int) -> bool:
    try:
        parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    except Exception:  # noqa: BLE001
        return False
    if (
        not parquet_path.is_file()
        or not mart_meta_path(parquet_path).is_file()
    ):
        return False
    return ensure_compute_sidecars(parquet_path)


def _load_status(*, route_set_id: int) -> RouteMartWarmStatus | None:
    value = cache.get(
        route_mart_warm_status_cache_key(route_set_id=route_set_id),
    )
    return value if isinstance(value, RouteMartWarmStatus) else None


def init_route_mart_warm_status(
    *,
    route_set_id: int,
    refs_version: str,
    phase: MartWarmPhase = "queued",
) -> RouteMartWarmStatus:
    now = time.time()
    status = RouteMartWarmStatus(
        route_set_id=route_set_id,
        refs_version=refs_version,
        phase=phase,
        started_at=now,
        updated_at=now,
    )
    cache.set(
        route_mart_warm_status_cache_key(route_set_id=route_set_id),
        status,
        REFS_VERSION_CACHE_SECONDS,
    )
    return status


def update_route_mart_warm_status(
    *,
    route_set_id: int,
    **fields: object,
) -> RouteMartWarmStatus | None:
    status = _load_status(route_set_id=route_set_id)
    if status is None:
        refs_version = fields.get("refs_version")
        if not isinstance(refs_version, str) or not refs_version:
            return None
        status = init_route_mart_warm_status(
            route_set_id=route_set_id,
            refs_version=refs_version,
            phase=(
                fields.get("phase")
                if isinstance(fields.get("phase"), str)
                else "queued"
            ),
        )
        fields = {
            key: value
            for key, value in fields.items()
            if key not in {"refs_version", "phase"}
        }

    for key, value in fields.items():
        if hasattr(status, key):
            setattr(status, key, value)
    status.updated_at = time.time()
    cache.set(
        route_mart_warm_status_cache_key(route_set_id=route_set_id),
        status,
        REFS_VERSION_CACHE_SECONDS,
    )
    return status


def mark_route_mart_warm_error(*, route_set_id: int, error: str) -> None:
    update_route_mart_warm_status(
        route_set_id=route_set_id,
        phase="error",
        error=error,
    )


def get_route_mart_warm_status(*, route_set_id: int) -> dict[str, Any] | None:
    status = _load_status(route_set_id=route_set_id)
    if status is None:
        return None
    return _status_to_api(status)


def _status_to_api(status: RouteMartWarmStatus) -> dict[str, Any]:
    mart_ready = is_route_mart_ready(route_set_id=status.route_set_id)

    phase: MartWarmPhase = status.phase
    if phase != "error" and mart_ready:
        phase = "done"

    elapsed_ms = 0
    if status.started_at:
        elapsed_ms = max(0, int((time.time() - status.started_at) * 1000))

    return {
        "route_set_id": status.route_set_id,
        "refs_version": status.refs_version,
        "phase": phase,
        "mart_ready": mart_ready,
        "elapsed_ms": elapsed_ms,
        "error": status.error,
    }
