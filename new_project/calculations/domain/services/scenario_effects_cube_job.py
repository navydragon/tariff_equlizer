from __future__ import annotations

import hashlib
import json
import logging
import threading
import time
import uuid
from dataclasses import dataclass, field
from typing import Any, Callable, Literal

from django.core.cache import cache
from django.db import close_old_connections

from calculations.domain.dto.scenario_effects_cube import ScenarioEffectsCubeRequestDTO
from calculations.domain.services.scenario_effects_cache import CACHE_TIMEOUT_SECONDS
from scenarios.models import Scenario

logger = logging.getLogger(__name__)

CubeJobPhase = Literal["queued", "aggregating", "done", "error"]

JOB_PREFIX = "cube_aggregate_job"
ACTIVE_PREFIX = "cube_aggregate_active"

ProgressCallback = Callable[[int, str], None]


@dataclass
class CubeAggregateJob:
    job_id: str
    user_id: int
    scenario_id: int
    phase: CubeJobPhase = "queued"
    progress_pct: float = 0.0
    message: str = "В очереди на агрегацию…"
    error: str | None = None
    result: dict[str, Any] | None = None
    meta: dict[str, Any] = field(default_factory=dict)
    created_at: float = 0.0
    updated_at: float = 0.0


def _job_cache_key(*, job_id: str) -> str:
    return f"{JOB_PREFIX}:{job_id}"


def _active_cache_key(*, fingerprint: str) -> str:
    return f"{ACTIVE_PREFIX}:{fingerprint}"


def cube_request_fingerprint(
    *,
    user_id: int,
    scenario_id: int,
    request: ScenarioEffectsCubeRequestDTO,
) -> str:
    payload = {
        "user_id": user_id,
        "scenario_id": scenario_id,
        "cache_key": request.cache_key,
        "group_by": request.group_by,
        "group_by_inner": request.group_by_inner,
        "cargo_groups": sorted(request.cargo_groups),
        "holdings": sorted(request.holdings),
    }
    encoded = json.dumps(payload, sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(encoded.encode("utf-8")).hexdigest()[:24]


def _save_job(job: CubeAggregateJob) -> None:
    job.updated_at = time.time()
    cache.set(_job_cache_key(job_id=job.job_id), job, CACHE_TIMEOUT_SECONDS)


def _load_job(*, job_id: str) -> CubeAggregateJob | None:
    value = cache.get(_job_cache_key(job_id=job_id))
    return value if isinstance(value, CubeAggregateJob) else None


def _update_job(job_id: str, **fields: object) -> CubeAggregateJob | None:
    job = _load_job(job_id=job_id)
    if job is None:
        return None
    for key, value in fields.items():
        if hasattr(job, key):
            setattr(job, key, value)
    _save_job(job)
    return job


def start_cube_aggregate_job(
    *,
    scenario: Scenario,
    user_id: int,
    request: ScenarioEffectsCubeRequestDTO,
) -> tuple[str | None, list[str]]:
    fingerprint = cube_request_fingerprint(
        user_id=user_id,
        scenario_id=scenario.id,
        request=request,
    )
    active_key = _active_cache_key(fingerprint=fingerprint)
    existing_job_id = cache.get(active_key)
    if isinstance(existing_job_id, str):
        existing = _load_job(job_id=existing_job_id)
        if existing is not None and existing.phase in {"queued", "aggregating"}:
            return existing_job_id, []

    now = time.time()
    job = CubeAggregateJob(
        job_id=uuid.uuid4().hex,
        user_id=user_id,
        scenario_id=scenario.id,
        created_at=now,
        updated_at=now,
    )
    _save_job(job)
    cache.set(active_key, job.job_id, CACHE_TIMEOUT_SECONDS)

    thread = threading.Thread(
        target=_run_cube_aggregate_job,
        kwargs={
            "job_id": job.job_id,
            "scenario_id": scenario.id,
            "user_id": user_id,
            "request": request,
            "fingerprint": fingerprint,
        },
        name=f"cube-aggregate-{scenario.id}",
        daemon=True,
    )
    thread.start()
    return job.job_id, []


def get_cube_job_status(
    *,
    job_id: str,
    user_id: int,
) -> dict[str, Any] | None:
    job = _load_job(job_id=job_id)
    if job is None:
        return None
    if job.user_id != user_id:
        return None
    payload: dict[str, Any] = {
        "job_id": job.job_id,
        "phase": job.phase,
        "progress_pct": job.progress_pct,
        "message": job.message,
        "done": job.phase == "done",
        "error": job.error,
    }
    if job.phase == "done" and job.result is not None:
        payload["result"] = job.result
        if job.meta:
            payload["elapsed_ms"] = job.meta.get("elapsed_ms")
            payload["timings"] = job.meta.get("timings")
    return payload


def _run_cube_aggregate_job(
    *,
    job_id: str,
    scenario_id: int,
    user_id: int,
    request: ScenarioEffectsCubeRequestDTO,
    fingerprint: str,
) -> None:
    close_old_connections()
    try:
        _update_job(
            job_id,
            phase="aggregating",
            progress_pct=1,
            message="Подготовка агрегации…",
        )

        def on_progress(pct: int, message: str) -> None:
            _update_job(
                job_id,
                phase="aggregating",
                progress_pct=max(0, min(99, float(pct))),
                message=message,
            )

        from calculations.domain.services.scenario_effects_cube import (
            ScenarioEffectsCubeService,
        )

        scenario = Scenario.objects.get(pk=scenario_id)
        service = ScenarioEffectsCubeService()
        response_dto, errors, meta = service.aggregate(
            scenario=scenario,
            user_id=user_id,
            request=request,
            on_progress=on_progress,
        )
        if errors:
            _update_job(
                job_id,
                phase="error",
                progress_pct=0,
                message="Ошибка агрегации",
                error="; ".join(errors),
            )
            return

        assert response_dto is not None
        result = response_dto.to_api_dict()
        _update_job(
            job_id,
            phase="done",
            progress_pct=100,
            message="Готово",
            result=result,
            meta=meta,
            error=None,
        )
    except Exception:
        logger.exception("Cube aggregate job failed job_id=%s scenario_id=%s", job_id, scenario_id)
        _update_job(
            job_id,
            phase="error",
            progress_pct=0,
            message="Ошибка агрегации",
            error="Не удалось собрать куб эффектов",
        )
    finally:
        cache.delete(_active_cache_key(fingerprint=fingerprint))
        close_old_connections()
