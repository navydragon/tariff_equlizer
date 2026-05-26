from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pandas as pd
from django.conf import settings
from django.core.cache import cache
from django.db import transaction
from django.utils import timezone

from calculations.domain.services.scenario_effects_compact import _DIMENSION_COLUMNS
from core.models import RouteSet, Setting

META_SUFFIX = ".meta.json"

ROUTE_MART_REFS_VERSION_CODE = "route_mart_refs_version"
REFS_VERSION_CACHE_SECONDS = 60 * 60 * 24


def route_mart_cache_root() -> Path:
    configured = getattr(settings, "ROUTE_MART_CACHE_DIR", None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "cache" / "route_mart"


def route_mart_cache_dir(*, route_set_id: int) -> Path:
    return route_mart_cache_root() / str(route_set_id)


def get_route_mart_refs_version() -> str:
    cached = cache.get(ROUTE_MART_REFS_VERSION_CODE)
    if isinstance(cached, str) and cached:
        return cached

    try:
        value = Setting.objects.values_list("value", flat=True).get(
            code=ROUTE_MART_REFS_VERSION_CODE,
        )
    except Setting.DoesNotExist:
        value = "0"

    value_str = str(value or "0")
    cache.set(ROUTE_MART_REFS_VERSION_CODE, value_str, REFS_VERSION_CACHE_SECONDS)
    return value_str


def bump_route_mart_refs_version() -> str:
    """Инкремент глобальной версии справочников (для инвалидации parquet-витрин)."""
    with transaction.atomic():
        setting, _created = Setting.objects.select_for_update().get_or_create(
            code=ROUTE_MART_REFS_VERSION_CODE,
            defaults={"description": "Route mart refs version", "value": "0"},
        )
        try:
            current = int((setting.value or "0").strip() or "0")
        except ValueError:
            current = 0
        new_value = str(current + 1)
        setting.value = new_value
        setting.save(update_fields=["value"])

    cache.set(ROUTE_MART_REFS_VERSION_CODE, new_value, REFS_VERSION_CACHE_SECONDS)
    return new_value


def _format_updated_at(updated_at) -> str:
    if updated_at is None:
        return "0"
    if timezone.is_naive(updated_at):
        updated_at = timezone.make_aware(updated_at, timezone.get_current_timezone())
    return updated_at.strftime("%Y%m%dT%H%M%S%fZ")


def mart_parquet_path(*, route_set_id: int, updated_at, refs_version: str) -> Path:
    stamp = _format_updated_at(updated_at)
    filename = f"refs{refs_version}_{stamp}.parquet"
    return route_mart_cache_dir(route_set_id=route_set_id) / filename


def resolve_mart_parquet_path(*, route_set_id: int) -> Path:
    rs = RouteSet.objects.only("updated_at").get(pk=route_set_id)
    refs_version = get_route_mart_refs_version()
    return mart_parquet_path(
        route_set_id=route_set_id,
        updated_at=rs.updated_at,
        refs_version=refs_version,
    )


@dataclass
class MartMeta:
    dimension_labels: dict[str, list[str]]
    skipped_charge: int = 0
    routes_without_volume: int = 0
    row_count: int = 0
    filter_options: dict[str, list[str]] | None = None


def mart_meta_path(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(parquet_path.suffix + META_SUFFIX)


def encode_mart_dimensions(df: pd.DataFrame) -> dict[str, list[str]]:
    dimension_labels: dict[str, list[str]] = {}
    for column in _DIMENSION_COLUMNS:
        if column not in df.columns:
            continue
        codes, uniques = pd.factorize(df[column].astype(str), sort=False)
        df[f"dim_{column}"] = codes.astype(np.int32, copy=False)
        dimension_labels[column] = uniques.tolist()
    return dimension_labels


def build_filter_options_from_labels(dimension_labels: dict[str, list[str]]) -> dict[str, list[str]]:
    cargo_groups = set(dimension_labels.get("cargo_group", []))
    cargo_groups.add("—")
    holdings = set(dimension_labels.get("holding", [])) or {"Прочие"}
    return {
        "cargo_groups": sorted(cargo_groups),
        "holdings": sorted(holdings),
    }


def save_mart_meta(
    *,
    parquet_path: Path,
    meta: MartMeta,
) -> None:
    path = mart_meta_path(parquet_path)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    payload = {
        "dimension_labels": meta.dimension_labels,
        "skipped_charge": meta.skipped_charge,
        "routes_without_volume": meta.routes_without_volume,
        "row_count": meta.row_count,
        "filter_options": meta.filter_options,
    }
    tmp_path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    os.replace(tmp_path, path)


def load_mart_meta(parquet_path: Path) -> MartMeta | None:
    path = mart_meta_path(parquet_path)
    if not path.is_file():
        return None
    payload = json.loads(path.read_text(encoding="utf-8"))
    return MartMeta(
        dimension_labels=payload.get("dimension_labels") or {},
        skipped_charge=int(payload.get("skipped_charge", 0)),
        routes_without_volume=int(payload.get("routes_without_volume", 0)),
        row_count=int(payload.get("row_count", 0)),
        filter_options=payload.get("filter_options"),
    )


def _cleanup_stale_parquet_files(*, cache_dir: Path, keep_path: Path) -> int:
    removed = 0
    if not cache_dir.is_dir():
        return removed
    keep_resolved = keep_path.resolve()
    for entry in cache_dir.glob("*.parquet"):
        if entry.resolve() == keep_resolved:
            continue
        try:
            entry.unlink()
            removed += 1
        except OSError:
            pass
    return removed


def load_route_mart_parquet(path: Path) -> pd.DataFrame:
    return pd.read_parquet(path, engine="pyarrow")


def save_route_mart_parquet(df: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = path.with_suffix(path.suffix + ".tmp")
    try:
        df.to_parquet(
            tmp_path,
            engine="pyarrow",
            index=False,
            compression="snappy",
        )
        os.replace(tmp_path, path)
    finally:
        if tmp_path.exists():
            try:
                tmp_path.unlink()
            except OSError:
                pass


def try_load_route_mart(
    *,
    route_set_id: int,
) -> tuple[pd.DataFrame | None, MartMeta | None, dict[str, int | str]]:
    timings: dict[str, int | str] = {}
    t0 = time.perf_counter()

    path = resolve_mart_parquet_path(route_set_id=route_set_id)
    timings["mart_cache_path"] = str(path)
    t_resolve = time.perf_counter()
    timings["mart_cache_resolve_ms"] = int((t_resolve - t0) * 1000)

    if not path.is_file():
        timings["cache_hit"] = 0
        timings["parquet_read_ms"] = 0
        return None, None, timings

    t_read = time.perf_counter()
    df = load_route_mart_parquet(path)
    meta = load_mart_meta(path)
    t_done = time.perf_counter()

    timings["cache_hit"] = 1
    timings["parquet_read_ms"] = int((t_done - t_read) * 1000)
    timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))
    return df, meta, timings


def save_route_mart(
    *,
    route_set_id: int,
    df: pd.DataFrame,
    skipped_charge: int = 0,
    routes_without_volume: int = 0,
) -> dict[str, int | str]:
    timings: dict[str, int | str] = {}
    t0 = time.perf_counter()

    path = resolve_mart_parquet_path(route_set_id=route_set_id)
    timings["mart_cache_path"] = str(path)
    path.parent.mkdir(parents=True, exist_ok=True)

    dimension_labels = encode_mart_dimensions(df)
    filter_options = build_filter_options_from_labels(dimension_labels)
    save_mart_meta(
        parquet_path=path,
        meta=MartMeta(
            dimension_labels=dimension_labels,
            skipped_charge=skipped_charge,
            routes_without_volume=routes_without_volume,
            row_count=len(df),
            filter_options=filter_options,
        ),
    )
    save_route_mart_parquet(df, path)
    t_write = time.perf_counter()
    timings["parquet_write_ms"] = int((t_write - t0) * 1000)
    timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))

    removed = _cleanup_stale_parquet_files(
        cache_dir=path.parent,
        keep_path=path,
    )
    timings["mart_cache_cleanup_removed"] = removed
    return timings
