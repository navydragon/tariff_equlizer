from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path

import numpy as np

from calculations.domain.services.pandas_tariff_conditions import build_rule_mask_numpy
from calculations.domain.services.route_mart_store import (
    MartMeta,
    get_route_mart_refs_version,
    load_mart_meta,
    resolve_mart_parquet_path,
)
from core.models import RouteSet


def route_mask_cache_root() -> Path:
    from django.conf import settings

    configured = getattr(settings, "ROUTE_MASK_CACHE_DIR", None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "cache" / "route_masks"


def _format_updated_at(updated_at) -> str:
    from django.utils import timezone

    if updated_at is None:
        return "0"
    if timezone.is_naive(updated_at):
        updated_at = timezone.make_aware(updated_at, timezone.get_current_timezone())
    return updated_at.strftime("%Y%m%dT%H%M%S%fZ")


def mask_cache_dir(*, route_set_id: int) -> Path:
    rs = RouteSet.objects.only("updated_at").get(pk=route_set_id)
    refs_version = get_route_mart_refs_version()
    stamp = _format_updated_at(rs.updated_at)
    return route_mask_cache_root() / str(route_set_id) / f"refs{refs_version}_{stamp}"


def _conditions_hash(conditions: list[dict]) -> str:
    payload = json.dumps(conditions or [], sort_keys=True, ensure_ascii=False)
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()[:16]


def mask_path(*, cache_dir: Path, rule_id: int, conditions: list[dict]) -> Path:
    return cache_dir / f"rule_{rule_id}_{_conditions_hash(conditions)}.npy"


def try_load_rule_mask(
    *,
    route_set_id: int,
    rule_id: int,
    conditions: list[dict],
    n_routes: int,
    cache_dir: Path | None = None,
) -> np.ndarray | None:
    resolved_dir = cache_dir or mask_cache_dir(route_set_id=route_set_id)
    path = mask_path(cache_dir=resolved_dir, rule_id=rule_id, conditions=conditions)
    if not path.is_file():
        return None
    mask = np.load(path)
    if mask.shape != (n_routes,) or mask.dtype != np.bool_:
        return None
    return mask


def save_rule_mask(
    *,
    route_set_id: int,
    rule_id: int,
    conditions: list[dict],
    mask: np.ndarray,
    cache_dir: Path | None = None,
) -> None:
    resolved_dir = cache_dir or mask_cache_dir(route_set_id=route_set_id)
    resolved_dir.mkdir(parents=True, exist_ok=True)
    path = mask_path(cache_dir=resolved_dir, rule_id=rule_id, conditions=conditions)
    tmp_base = path.with_name(path.stem + ".tmp")
    np.save(tmp_base, mask.astype(np.bool_, copy=False))
    tmp_path = Path(f"{tmp_base}.npy")
    os.replace(tmp_path, path)


def build_or_load_rule_mask(
    *,
    route_set_id: int,
    rule_id: int,
    conditions: list[dict],
    df,
    mart_meta: MartMeta | None,
    cache_dir: Path | None = None,
) -> np.ndarray:
    n_routes = len(df)
    cached = try_load_rule_mask(
        route_set_id=route_set_id,
        rule_id=rule_id,
        conditions=conditions,
        n_routes=n_routes,
        cache_dir=cache_dir,
    )
    if cached is not None:
        return cached

    mask = build_rule_mask_numpy(df, conditions, mart_meta=mart_meta).astype(np.bool_, copy=False)
    save_rule_mask(
        route_set_id=route_set_id,
        rule_id=rule_id,
        conditions=conditions,
        mask=mask,
        cache_dir=cache_dir,
    )
    return mask


def resolve_mart_meta_for_route_set(*, route_set_id: int) -> MartMeta | None:
    path = resolve_mart_parquet_path(route_set_id=route_set_id)
    return load_mart_meta(path)
