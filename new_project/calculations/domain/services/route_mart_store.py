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
CHARGE_NPY_SUFFIX = ".charge.npy"
DIMS_NPZ_SUFFIX = ".dims.npz"
MASKS_NPZ_SUFFIX = ".masks.npz"

MART_COMPUTE_BASE_COLUMNS = ("freight_charge_rub",)

# Доп. измерения для масок правил (кодируются в dims.npz, не в masks.npz).
_MART_MASK_DIM_SOURCES: dict[str, str] = {
    "origin_railroad": "origin_railroad_code",
    "destination_railroad": "destination_railroad_code",
}

# Колонки для masks.npz: только числовые поля, не покрытые dim_*.
MART_RULE_MASK_SIDECAR_COLUMNS = (
    "distance_belt",
    "distance_belt_midpoint_km",
    "special_container_type",
    "shipper_id",
    "shipment_type_id",
    "message_type_id",
)

_MASK_SIDECAR_INT_COLUMNS = frozenset(
    {"shipper_id", "shipment_type_id", "message_type_id"},
)

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


def charge_npy_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + CHARGE_NPY_SUFFIX)


def dims_npz_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + DIMS_NPZ_SUFFIX)


def masks_npz_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + MASKS_NPZ_SUFFIX)


def is_rules_light_mart_columns(columns: list[str] | None) -> bool:
    if columns is None:
        return False
    return columns == resolve_light_mart_columns(has_rules=True)


def resolve_light_mart_columns(*, has_rules: bool) -> list[str]:
    """Минимальный набор колонок для синхронного KPI-расчёта."""
    if not has_rules:
        return list(MART_COMPUTE_BASE_COLUMNS)
    columns = list(MART_COMPUTE_BASE_COLUMNS)
    for column in _DIMENSION_COLUMNS:
        dim_column = f"dim_{column}"
        if dim_column not in columns:
            columns.append(dim_column)
    for param in _MART_MASK_DIM_SOURCES:
        dim_column = f"dim_{param}"
        if dim_column not in columns:
            columns.append(dim_column)
    for column in MART_RULE_MASK_SIDECAR_COLUMNS:
        if column not in columns:
            columns.append(column)
    return columns


def _parquet_column_names(path: Path) -> set[str]:
    import pyarrow.parquet as pq

    return set(pq.ParquetFile(path).schema_arrow.names)


def _filter_existing_columns(path: Path, columns: list[str]) -> list[str]:
    available = _parquet_column_names(path)
    selected = [column for column in columns if column in available]
    if not selected:
        return list(MART_COMPUTE_BASE_COLUMNS)
    return selected


def encode_mart_dimensions(df: pd.DataFrame) -> dict[str, list[str]]:
    dimension_labels: dict[str, list[str]] = {}
    for column in _DIMENSION_COLUMNS:
        if column not in df.columns:
            continue
        codes, uniques = pd.factorize(df[column].astype(str), sort=False)
        df[f"dim_{column}"] = codes.astype(np.int32, copy=False)
        dimension_labels[column] = uniques.tolist()
    for param, source_column in _MART_MASK_DIM_SOURCES.items():
        if source_column not in df.columns:
            continue
        codes, uniques = pd.factorize(df[source_column].astype(str), sort=False)
        df[f"dim_{param}"] = codes.astype(np.int32, copy=False)
        dimension_labels[param] = uniques.tolist()
    return dimension_labels


def _dim_npz_column_names() -> list[str]:
    columns = [f"dim_{column}" for column in _DIMENSION_COLUMNS]
    columns.extend(f"dim_{param}" for param in _MART_MASK_DIM_SOURCES)
    return columns


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


def _atomic_replace(tmp_path: Path, final_path: Path, *, max_attempts: int = 12) -> None:
    import time

    final_path.parent.mkdir(parents=True, exist_ok=True)
    last_error: OSError | None = None
    for attempt in range(max_attempts):
        try:
            if final_path.exists():
                final_path.unlink()
            os.replace(tmp_path, final_path)
            return
        except OSError as exc:
            last_error = exc
            if attempt + 1 >= max_attempts:
                break
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


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


def load_route_mart_parquet(
    path: Path,
    *,
    columns: list[str] | None = None,
) -> pd.DataFrame:
    import pyarrow.parquet as pq

    if columns is None:
        return pq.read_table(path, memory_map=True).to_pandas(
            split_blocks=True,
            self_destruct=True,
        )

    selected = _filter_existing_columns(path, columns)
    return pq.read_table(path, columns=selected, memory_map=True).to_pandas(
        split_blocks=True,
        self_destruct=True,
    )


def save_charge_npy(df: pd.DataFrame, parquet_path: Path) -> None:
    if "freight_charge_rub" not in df.columns:
        return
    out_path = charge_npy_path(parquet_path)
    tmp_base = out_path.parent / (out_path.stem + ".tmp")
    charge = df["freight_charge_rub"].to_numpy(dtype=np.float64, copy=False)
    np.save(tmp_base, charge)
    _atomic_replace(Path(f"{tmp_base}.npy"), out_path)


def load_charge_npy(parquet_path: Path) -> np.ndarray | None:
    path = charge_npy_path(parquet_path)
    if not path.is_file():
        return None
    loaded = np.load(path, mmap_mode="r")
    return np.asarray(loaded, dtype=np.float64)


def ensure_charge_npy(parquet_path: Path) -> np.ndarray | None:
    """Создаёт sidecar при первом обращении к старой витрине без .charge.npy."""
    existing = load_charge_npy(parquet_path)
    if existing is not None:
        return existing
    if not parquet_path.is_file():
        return None
    charge_df = load_route_mart_parquet(
        parquet_path,
        columns=list(MART_COMPUTE_BASE_COLUMNS),
    )
    if charge_df.empty or "freight_charge_rub" not in charge_df.columns:
        return None
    save_charge_npy(charge_df, parquet_path)
    return charge_df["freight_charge_rub"].to_numpy(dtype=np.float64, copy=False)


def _mask_sidecar_columns_in_df(df: pd.DataFrame) -> list[str]:
    return [
        column
        for column in MART_RULE_MASK_SIDECAR_COLUMNS
        if column in df.columns
    ]


def _mask_sidecar_array(series: pd.Series, column: str) -> np.ndarray:
    if column in _MASK_SIDECAR_INT_COLUMNS:
        return (
            pd.to_numeric(series, errors="coerce")
            .fillna(-1)
            .to_numpy(dtype=np.int32, copy=False)
        )
    if column == "distance_belt_midpoint_km":
        return pd.to_numeric(series, errors="coerce").to_numpy(
            dtype=np.float64,
            copy=False,
        )
    if column == "distance_belt":
        return series.fillna("").astype(str).to_numpy(dtype="U32", copy=False)
    if column == "special_container_type":
        return series.fillna("").astype(str).to_numpy(dtype="U128", copy=False)
    raise ValueError(f"Unexpected masks sidecar column: {column}")


def _dims_npz_needs_rebuild(parquet_path: Path) -> bool:
    path = dims_npz_path(parquet_path)
    if not path.is_file():
        return True
    available = _parquet_column_names(parquet_path)
    required: set[str] = set()
    for param, source_column in _MART_MASK_DIM_SOURCES.items():
        dim_column = f"dim_{param}"
        if dim_column in available or source_column in available:
            required.add(dim_column)
    if not required:
        return False
    try:
        with np.load(path, allow_pickle=False) as data:
            keys = set(data.files)
    except OSError:
        return True
    return bool(required - keys)


def _encode_mask_dims_into_df(
    df: pd.DataFrame,
    *,
    meta: MartMeta | None,
) -> MartMeta | None:
    updated_labels = dict(meta.dimension_labels) if meta is not None else {}
    for param, source_column in _MART_MASK_DIM_SOURCES.items():
        dim_column = f"dim_{param}"
        if dim_column in df.columns or source_column not in df.columns:
            continue
        codes, uniques = pd.factorize(df[source_column].astype(str), sort=False)
        df[dim_column] = codes.astype(np.int32, copy=False)
        updated_labels[param] = uniques.tolist()
    if meta is None:
        return None
    return MartMeta(
        dimension_labels=updated_labels,
        skipped_charge=meta.skipped_charge,
        routes_without_volume=meta.routes_without_volume,
        row_count=meta.row_count,
        filter_options=meta.filter_options,
    )


def _masks_npz_needs_rebuild(parquet_path: Path) -> bool:
    path = masks_npz_path(parquet_path)
    if not path.is_file():
        return True
    try:
        with np.load(path, allow_pickle=False) as data:
            keys = frozenset(data.files)
    except OSError:
        return True
    if not keys:
        return True
    allowed = frozenset(MART_RULE_MASK_SIDECAR_COLUMNS)
    if keys - allowed:
        return True
    available = _parquet_column_names(parquet_path)
    required = {
        column for column in MART_RULE_MASK_SIDECAR_COLUMNS if column in available
    }
    return bool(required - keys)


def save_dims_npz(df: pd.DataFrame, parquet_path: Path) -> None:
    arrays: dict[str, np.ndarray] = {}
    for dim_column in _dim_npz_column_names():
        if dim_column not in df.columns:
            continue
        arrays[dim_column] = df[dim_column].to_numpy(dtype=np.int32, copy=False)
    if not arrays:
        return
    out_path = dims_npz_path(parquet_path)
    tmp_path = out_path.parent / (out_path.stem + ".write.npz")
    np.savez(tmp_path, **arrays)
    _atomic_replace(tmp_path, out_path)


def save_masks_npz(df: pd.DataFrame, parquet_path: Path) -> None:
    arrays: dict[str, np.ndarray] = {}
    for column in _mask_sidecar_columns_in_df(df):
        arrays[column] = _mask_sidecar_array(df[column], column)
    if not arrays:
        return
    out_path = masks_npz_path(parquet_path)
    tmp_path = out_path.parent / (out_path.stem + ".write.npz")
    np.savez(tmp_path, **arrays)
    _atomic_replace(tmp_path, out_path)


def load_dims_npz(parquet_path: Path) -> dict[str, np.ndarray]:
    path = dims_npz_path(parquet_path)
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def load_masks_npz(parquet_path: Path) -> dict[str, np.ndarray]:
    path = masks_npz_path(parquet_path)
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as data:
        return {key: np.asarray(data[key]) for key in data.files}


def _sidecars_complete(parquet_path: Path) -> bool:
    return (
        charge_npy_path(parquet_path).is_file()
        and dims_npz_path(parquet_path).is_file()
        and masks_npz_path(parquet_path).is_file()
        and not _dims_npz_needs_rebuild(parquet_path)
        and not _masks_npz_needs_rebuild(parquet_path)
    )


def ensure_compute_sidecars(parquet_path: Path) -> bool:
    """Гарантирует charge.npy + dims.npz + masks.npz для витрины."""
    if _sidecars_complete(parquet_path):
        return True
    if not parquet_path.is_file():
        return False

    need_charge = not charge_npy_path(parquet_path).is_file()
    need_dims = _dims_npz_needs_rebuild(parquet_path)
    need_masks = _masks_npz_needs_rebuild(parquet_path)

    columns_to_read: list[str] = list(MART_COMPUTE_BASE_COLUMNS)
    if need_dims:
        for dim_column in _dim_npz_column_names():
            if dim_column not in columns_to_read:
                columns_to_read.append(dim_column)
        for source_column in _MART_MASK_DIM_SOURCES.values():
            if source_column not in columns_to_read:
                columns_to_read.append(source_column)
    if need_masks:
        for column in MART_RULE_MASK_SIDECAR_COLUMNS:
            if column not in columns_to_read:
                columns_to_read.append(column)

    df = load_route_mart_parquet(
        parquet_path,
        columns=_filter_existing_columns(parquet_path, columns_to_read),
    )
    if df.empty:
        return False

    meta = load_mart_meta(parquet_path)

    if need_charge:
        save_charge_npy(df, parquet_path)
    if need_dims:
        meta = _encode_mask_dims_into_df(df, meta=meta) or meta
        if dims_npz_path(parquet_path).is_file():
            try:
                dims_npz_path(parquet_path).unlink()
            except OSError:
                pass
        save_dims_npz(df, parquet_path)
        if meta is not None:
            save_mart_meta(parquet_path=parquet_path, meta=meta)
    if need_masks:
        if masks_npz_path(parquet_path).is_file():
            try:
                masks_npz_path(parquet_path).unlink()
            except OSError:
                pass
        save_masks_npz(df, parquet_path)
    return _sidecars_complete(parquet_path)


def load_mart_sidecar_dataframe(
    parquet_path: Path,
    *,
    include_charge: bool = True,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Собирает DataFrame из sidecar без чтения parquet."""
    timings: dict[str, int] = {}
    columns: dict[str, np.ndarray] = {}

    if include_charge:
        t_charge = time.perf_counter()
        charge = load_charge_npy(parquet_path)
        if charge is None:
            charge = ensure_charge_npy(parquet_path)
        if charge is not None:
            columns["freight_charge_rub"] = charge
        timings["charge_npy_read_ms"] = int((time.perf_counter() - t_charge) * 1000)

    t_dims = time.perf_counter()
    columns.update(load_dims_npz(parquet_path))
    timings["dims_npz_read_ms"] = int((time.perf_counter() - t_dims) * 1000)

    t_masks = time.perf_counter()
    columns.update(load_masks_npz(parquet_path))
    timings["masks_npz_read_ms"] = int((time.perf_counter() - t_masks) * 1000)

    if not columns:
        return pd.DataFrame(), timings
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        target_len = max(lengths)
        columns = {
            key: value
            for key, value in columns.items()
            if len(value) == target_len
        }
    if not columns:
        return pd.DataFrame(), timings
    return pd.DataFrame(columns), timings


def _cleanup_stale_sidecar_files(
    *,
    cache_dir: Path,
    keep_stem: str,
    suffix: str,
) -> int:
    removed = 0
    pattern = f"*{suffix}"
    keep_name = f"{keep_stem}{suffix}"
    for entry in cache_dir.glob(pattern):
        if entry.name == keep_name:
            continue
        try:
            entry.unlink()
            removed += 1
        except OSError:
            pass
    return removed


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
    columns: list[str] | None = None,
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

    meta = load_mart_meta(path)
    t_read = time.perf_counter()

    if columns is not None and columns == list(MART_COMPUTE_BASE_COLUMNS):
        charge = load_charge_npy(path)
        if charge is None:
            charge = ensure_charge_npy(path)
        if charge is not None:
            df = pd.DataFrame({"freight_charge_rub": charge})
            timings["charge_npy_read_ms"] = int((time.perf_counter() - t_read) * 1000)
            timings["parquet_read_ms"] = timings["charge_npy_read_ms"]
            timings["mart_read_mode"] = "charge_npy"
            timings["cache_hit"] = 1
            timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))
            return df, meta, timings

    if is_rules_light_mart_columns(columns):
        if ensure_compute_sidecars(path):
            df, sidecar_timings = load_mart_sidecar_dataframe(path, include_charge=True)
            if not df.empty and "freight_charge_rub" in df.columns:
                timings.update(sidecar_timings)
                total_read = (
                    timings.get("charge_npy_read_ms", 0)
                    + timings.get("dims_npz_read_ms", 0)
                    + timings.get("masks_npz_read_ms", 0)
                )
                timings["parquet_read_ms"] = total_read
                timings["mart_read_mode"] = "sidecar_npz"
                timings["cache_hit"] = 1
                timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))
                return df, meta, timings

    df = load_route_mart_parquet(path, columns=columns)
    t_done = time.perf_counter()

    timings["cache_hit"] = 1
    timings["parquet_read_ms"] = int((t_done - t_read) * 1000)
    timings["mart_read_mode"] = "parquet_columns" if columns else "parquet_full"
    if columns:
        timings["mart_read_columns"] = len(columns)
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
    save_charge_npy(df, path)
    save_dims_npz(df, path)
    save_masks_npz(df, path)
    t_write = time.perf_counter()
    timings["parquet_write_ms"] = int((t_write - t0) * 1000)
    timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))

    removed = _cleanup_stale_parquet_files(
        cache_dir=path.parent,
        keep_path=path,
    )
    keep_stem = path.stem
    for suffix in (CHARGE_NPY_SUFFIX, DIMS_NPZ_SUFFIX, MASKS_NPZ_SUFFIX):
        removed += _cleanup_stale_sidecar_files(
            cache_dir=path.parent,
            keep_stem=keep_stem,
            suffix=suffix,
        )
    timings["mart_cache_cleanup_removed"] = removed

    from calculations.domain.services.rule_mask_prewarm import (
        prewarm_rules_for_route_set,
    )

    timings["rule_masks_prewarmed"] = prewarm_rules_for_route_set(
        route_set_id=route_set_id,
    )
    return timings
