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
from core.domain.cargo.ordering import sort_cargo_group_names
from core.models import RouteSet, Setting

META_SUFFIX = ".meta.json"
CHARGE_NPY_SUFFIX = ".charge.npy"
VOLUME_NPY_SUFFIX = ".volume.npy"
DIMS_NPZ_SUFFIX = ".dims.npz"  # legacy, только для миграции
MASKS_NPZ_SUFFIX = ".masks.npz"  # legacy, только для миграции
DIM_NPY_SUFFIX = ".dim_"
MASK_NPY_SUFFIX = ".mask_"

MART_COMPUTE_BASE_COLUMNS = ("freight_charge_rub",)

# Slim-parquet: только колонки без sidecar (остальное — charge/dims/masks/volume npz).
MART_PARQUET_SLIM_COLUMNS = frozenset(
    {
        "transport_volume_tons",
        "cargo_group_code",
    },
)

# Доп. измерения для масок правил (кодируются в dims.npz, не в masks.npz).
_MART_MASK_DIM_SOURCES: dict[str, str] = {
    "origin_railroad": "origin_railroad_code",
    "destination_railroad": "destination_railroad_code",
}

# Колонки для masks.npz: только числовые поля, не покрытые dim_*.
MART_MASK_LABEL_COLUMNS = (
    "cargo_code_3",
    "cargo_code_izpod_3",
    "cargo_group_izpod",
    "distance_belt",
    "special_container_type",
)

MART_RULE_MASK_SIDECAR_COLUMNS = (
    "distance_belt",
    "distance_belt_midpoint_km",
    "special_container_type",
    "cargo_code_3",
    "cargo_code_izpod_3",
    "cargo_group_izpod",
    "shipper_id",
    "shipment_type_id",
    "message_type_id",
)

_MASK_SIDECAR_INT_COLUMNS = frozenset(
    {"shipper_id", "shipment_type_id", "message_type_id"},
)

# Версия sidecar на диске (отдельные .npy + mmap); bump при смене dtype/колонок.
SIDECAR_SCHEMA_VERSION = 4
# Legacy npz (до v4).
MASKS_NPZ_SCHEMA_VERSION = 3
MASKS_NPZ_META_KEYS = frozenset({"__schema_version__"})

# Строковые mask-колонки хранятся как factorize-коды (uint8/uint16), labels — в meta.
_MASK_SIDECAR_FACTORIZE_COLUMNS = frozenset(
    {
        "distance_belt",
        "special_container_type",
        "cargo_code_3",
        "cargo_code_izpod_3",
        "cargo_group_izpod",
    },
)

# Колонки slim-parquet; fat-витрина (legacy) инвалидируется при загрузке.
MART_PARQUET_REQUIRED_COLUMNS = MART_PARQUET_SLIM_COLUMNS

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
    sidecar_schema_version: int = 0


@dataclass
class MartSidecarView:
    """Column-oriented mmap sidecar для KPI/масок без pandas DataFrame."""

    column_arrays: dict[str, np.ndarray]

    @property
    def empty(self) -> bool:
        return len(self) == 0

    def __len__(self) -> int:
        if not self.column_arrays:
            return 0
        return int(len(next(iter(self.column_arrays.values()))))

    def __contains__(self, key: str) -> bool:
        return key in self.column_arrays

    @property
    def column_names(self) -> frozenset[str]:
        return frozenset(self.column_arrays.keys())

    @property
    def columns(self) -> frozenset[str]:
        """Имена колонок (совместимость с `'col' in df.columns`)."""
        return self.column_names

    def __getitem__(self, key: str) -> np.ndarray:
        return self.column_arrays[key]

    def get(self, key: str, default=None):
        return self.column_arrays.get(key, default)

    def to_dataframe(self) -> pd.DataFrame:
        if self.empty:
            return pd.DataFrame()
        return pd.DataFrame(self.column_arrays)


def mart_meta_path(parquet_path: Path) -> Path:
    return parquet_path.with_suffix(parquet_path.suffix + META_SUFFIX)


def charge_npy_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + CHARGE_NPY_SUFFIX)


def volume_npy_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + VOLUME_NPY_SUFFIX)


def dims_npz_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + DIMS_NPZ_SUFFIX)


def masks_npz_path(parquet_path: Path) -> Path:
    return parquet_path.with_name(parquet_path.stem + MASKS_NPZ_SUFFIX)


def dim_npy_path(parquet_path: Path, dim_column: str) -> Path:
    return parquet_path.with_name(f"{parquet_path.stem}{DIM_NPY_SUFFIX}{dim_column.removeprefix('dim_')}.npy")


def mask_npy_path(parquet_path: Path, column: str) -> Path:
    return parquet_path.with_name(f"{parquet_path.stem}{MASK_NPY_SUFFIX}{column}.npy")


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
    return [column for column in columns if column in available]


def _parquet_schema_is_current(parquet_path: Path) -> bool:
    available = _parquet_column_names(parquet_path)
    return available == set(MART_PARQUET_SLIM_COLUMNS)


def _parquet_has_sidecar_source_columns(parquet_path: Path) -> bool:
    """Legacy fat-parquet содержит колонки для пересборки sidecar без SQL."""
    if not _parquet_schema_is_current(parquet_path):
        available = _parquet_column_names(parquet_path)
        return bool(
            set(MART_RULE_MASK_SIDECAR_COLUMNS) & available
            or set(_dim_npz_column_names()) & available
        )
    return False


def _compact_int_codes(array: np.ndarray) -> np.ndarray:
    if array.size == 0:
        return array.astype(np.int32, copy=False)
    max_value = int(np.max(array))
    if max_value <= 255:
        return array.astype(np.uint8, copy=False)
    if max_value <= 65535:
        return array.astype(np.uint16, copy=False)
    return array.astype(np.int32, copy=False)


def _build_slim_parquet_dataframe(df: pd.DataFrame) -> pd.DataFrame:
    slim: dict[str, np.ndarray] = {}
    if "transport_volume_tons" in df.columns:
        slim["transport_volume_tons"] = (
            pd.to_numeric(df["transport_volume_tons"], errors="coerce")
            .fillna(0.0)
            .to_numpy(dtype=np.float32, copy=False)
        )
    if "cargo_group_code" in df.columns:
        slim["cargo_group_code"] = (
            pd.to_numeric(df["cargo_group_code"], errors="coerce")
            .fillna(0)
            .to_numpy(dtype=np.uint16, copy=False)
        )
    return pd.DataFrame(slim)


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
        "cargo_groups": sort_cargo_group_names(cargo_groups),
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
        "sidecar_schema_version": meta.sidecar_schema_version,
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
        sidecar_schema_version=int(payload.get("sidecar_schema_version", 0)),
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
    charge = (
        pd.to_numeric(df["freight_charge_rub"], errors="coerce")
        .to_numpy(dtype=np.float64, copy=False)
    )
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
    if _parquet_schema_is_current(parquet_path):
        return None
    charge_df = load_route_mart_parquet(
        parquet_path,
        columns=list(MART_COMPUTE_BASE_COLUMNS),
    )
    if charge_df.empty or "freight_charge_rub" not in charge_df.columns:
        return None
    save_charge_npy(charge_df, parquet_path)
    return charge_df["freight_charge_rub"].to_numpy(dtype=np.float64, copy=False)


def save_volume_npy(df: pd.DataFrame, parquet_path: Path) -> None:
    if "transport_volume_tons" not in df.columns:
        return
    out_path = volume_npy_path(parquet_path)
    tmp_base = out_path.parent / (out_path.stem + ".tmp")
    volume = (
        pd.to_numeric(df["transport_volume_tons"], errors="coerce")
        .fillna(0.0)
        .to_numpy(dtype=np.float32, copy=False)
    )
    np.save(tmp_base, volume)
    _atomic_replace(Path(f"{tmp_base}.npy"), out_path)


def load_volume_npy(parquet_path: Path) -> np.ndarray | None:
    path = volume_npy_path(parquet_path)
    if not path.is_file():
        return None
    loaded = np.load(path, mmap_mode="r")
    return np.asarray(loaded, dtype=np.float32)


def ensure_volume_npy(parquet_path: Path) -> np.ndarray | None:
    existing = load_volume_npy(parquet_path)
    if existing is not None:
        return existing
    if not parquet_path.is_file():
        return None
    volume_df = load_route_mart_parquet(
        parquet_path,
        columns=["transport_volume_tons"],
    )
    if volume_df.empty or "transport_volume_tons" not in volume_df.columns:
        return None
    save_volume_npy(volume_df, parquet_path)
    return load_volume_npy(parquet_path)


def _mask_sidecar_columns_in_df(df: pd.DataFrame) -> list[str]:
    return [
        column
        for column in MART_RULE_MASK_SIDECAR_COLUMNS
        if column in df.columns
    ]


def _mask_sidecar_array(series: pd.Series, column: str) -> np.ndarray | None:
    if column in _MASK_SIDECAR_INT_COLUMNS:
        numeric = pd.to_numeric(series, errors="coerce")
        if column == "shipper_id":
            return (
                numeric.fillna(0)
                .to_numpy(dtype=np.uint16, copy=False)
            )
        return (
            numeric.fillna(0)
            .to_numpy(dtype=np.uint16, copy=False)
        )
    if column == "distance_belt_midpoint_km":
        return (
            pd.to_numeric(series, errors="coerce")
            .fillna(0)
            .to_numpy(dtype=np.uint16, copy=False)
        )
    if column in _MASK_SIDECAR_FACTORIZE_COLUMNS:
        filled = series.fillna("").astype(str).str.strip()
        if filled.eq("").all():
            return None
        codes, _uniques = pd.factorize(filled, sort=False)
        return _compact_int_codes(codes.astype(np.int32, copy=False))
    if column in MART_RULE_MASK_SIDECAR_COLUMNS:
        filled = series.fillna("").astype(str)
        if filled.str.strip().eq("").all():
            return None
        codes, _uniques = pd.factorize(filled, sort=False)
        return _compact_int_codes(codes.astype(np.int32, copy=False))
    raise ValueError(f"Unexpected masks sidecar column: {column}")


def _save_npy_array(array: np.ndarray, out_path: Path) -> None:
    tmp_base = out_path.parent / (out_path.stem + ".tmp")
    np.save(tmp_base, array)
    _atomic_replace(Path(f"{tmp_base}.npy"), out_path)


def _load_npy_mmap(path: Path) -> np.ndarray | None:
    if not path.is_file():
        return None
    loaded = np.load(path, mmap_mode="r")
    return np.asarray(loaded)


def _list_dim_npy_columns(parquet_path: Path) -> set[str]:
    prefix = f"{parquet_path.stem}{DIM_NPY_SUFFIX}"
    suffix = ".npy"
    columns: set[str] = set()
    for entry in parquet_path.parent.glob(f"{prefix}*{suffix}"):
        if not entry.name.startswith(prefix):
            continue
        name = entry.name[len(prefix) : -len(suffix)]
        columns.add(f"dim_{name}")
    return columns


def _list_mask_npy_columns(parquet_path: Path) -> set[str]:
    prefix = f"{parquet_path.stem}{MASK_NPY_SUFFIX}"
    suffix = ".npy"
    columns: set[str] = set()
    for entry in parquet_path.parent.glob(f"{prefix}*{suffix}"):
        if not entry.name.startswith(prefix):
            continue
        columns.add(entry.name[len(prefix) : -len(suffix)])
    return columns


def _remove_legacy_npz_sidecars(parquet_path: Path) -> None:
    for path_fn in (dims_npz_path, masks_npz_path):
        path = path_fn(parquet_path)
        if path.is_file():
            try:
                path.unlink()
            except OSError:
                pass


def _remove_stale_sidecar_npy_files(
    *,
    cache_dir: Path,
    keep_stem: str,
) -> int:
    removed = 0
    dim_prefix = f"{keep_stem}{DIM_NPY_SUFFIX}"
    mask_prefix = f"{keep_stem}{MASK_NPY_SUFFIX}"
    for entry in cache_dir.glob("*.npy"):
        name = entry.name
        if name.startswith(dim_prefix) or name.startswith(mask_prefix):
            continue
        if f"{DIM_NPY_SUFFIX}" in name or f"{MASK_NPY_SUFFIX}" in name:
            try:
                entry.unlink()
                removed += 1
            except OSError:
                pass
    return removed


def _dims_npy_needs_rebuild(parquet_path: Path) -> bool:
    if dims_npz_path(parquet_path).is_file():
        return True
    meta = load_mart_meta(parquet_path)
    if meta is None or meta.sidecar_schema_version < SIDECAR_SCHEMA_VERSION:
        return True
    present = _list_dim_npy_columns(parquet_path)
    required = set(_dim_npz_column_names())
    return bool(required - present)


def _masks_npy_needs_rebuild(parquet_path: Path) -> bool:
    if masks_npz_path(parquet_path).is_file():
        return True
    meta = load_mart_meta(parquet_path)
    if meta is None or meta.sidecar_schema_version < SIDECAR_SCHEMA_VERSION:
        return True
    present = _list_mask_npy_columns(parquet_path)
    allowed = frozenset(MART_RULE_MASK_SIDECAR_COLUMNS)
    if present - allowed:
        return True
    return False


def _dims_npz_needs_rebuild(parquet_path: Path) -> bool:
    return _dims_npy_needs_rebuild(parquet_path)


def _masks_npz_needs_rebuild(parquet_path: Path) -> bool:
    return _masks_npy_needs_rebuild(parquet_path)


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
        sidecar_schema_version=meta.sidecar_schema_version,
    )


def _masks_npz_needs_rebuild_legacy(parquet_path: Path) -> bool:
    path = masks_npz_path(parquet_path)
    if not path.is_file():
        return True
    try:
        with np.load(path, allow_pickle=False) as data:
            keys = frozenset(data.files)
            if "__schema_version__" not in keys:
                return True
            schema_version = int(np.asarray(data["__schema_version__"]).reshape(-1)[0])
            if schema_version != MASKS_NPZ_SCHEMA_VERSION:
                return True
    except OSError:
        return True
    if not keys:
        return True
    data_keys = keys - MASKS_NPZ_META_KEYS
    allowed = frozenset(MART_RULE_MASK_SIDECAR_COLUMNS)
    if data_keys - allowed:
        return True
    return False


def save_dims_npy(df: pd.DataFrame, parquet_path: Path) -> None:
    for dim_column in _dim_npz_column_names():
        if dim_column not in df.columns:
            continue
        array = _compact_int_codes(
            df[dim_column].to_numpy(dtype=np.int32, copy=False),
        )
        _save_npy_array(array, dim_npy_path(parquet_path, dim_column))
    _remove_legacy_npz_sidecars(parquet_path)


def save_masks_npy(df: pd.DataFrame, parquet_path: Path) -> None:
    for column in _mask_sidecar_columns_in_df(df):
        array = _mask_sidecar_array(df[column], column)
        if array is None:
            continue
        _save_npy_array(array, mask_npy_path(parquet_path, column))
    _remove_legacy_npz_sidecars(parquet_path)


def save_dims_npy_from_arrays(
    arrays: dict[str, np.ndarray],
    parquet_path: Path,
) -> None:
    for dim_column, array in arrays.items():
        _save_npy_array(array, dim_npy_path(parquet_path, dim_column))
    _remove_legacy_npz_sidecars(parquet_path)


def save_masks_npy_from_arrays(
    arrays: dict[str, np.ndarray],
    parquet_path: Path,
) -> None:
    for column, array in arrays.items():
        if column in MASKS_NPZ_META_KEYS:
            continue
        _save_npy_array(array, mask_npy_path(parquet_path, column))
    _remove_legacy_npz_sidecars(parquet_path)


def load_dims_npy_mmap(parquet_path: Path) -> dict[str, np.ndarray]:
    columns: dict[str, np.ndarray] = {}
    for dim_column in _dim_npz_column_names():
        array = _load_npy_mmap(dim_npy_path(parquet_path, dim_column))
        if array is not None:
            columns[dim_column] = array
    return columns


def load_masks_npy_mmap(parquet_path: Path) -> dict[str, np.ndarray]:
    columns: dict[str, np.ndarray] = {}
    for column in _list_mask_npy_columns(parquet_path):
        array = _load_npy_mmap(mask_npy_path(parquet_path, column))
        if array is not None:
            columns[column] = array
    return columns


def _load_dims_npz_legacy(parquet_path: Path) -> dict[str, np.ndarray]:
    path = dims_npz_path(parquet_path)
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as data:
        return {key: data[key] for key in data.files}


def _load_masks_npz_legacy(parquet_path: Path) -> dict[str, np.ndarray]:
    path = masks_npz_path(parquet_path)
    if not path.is_file():
        return {}
    with np.load(path, allow_pickle=False) as data:
        return {
            key: np.asarray(data[key])
            for key in data.files
            if key not in MASKS_NPZ_META_KEYS
        }


def load_dims_npz(parquet_path: Path) -> dict[str, np.ndarray]:
    return load_dims_npy_mmap(parquet_path)


def load_masks_npz(parquet_path: Path) -> dict[str, np.ndarray]:
    return load_masks_npy_mmap(parquet_path)


def save_dims_npz(df: pd.DataFrame, parquet_path: Path) -> None:
    save_dims_npy(df, parquet_path)


def save_masks_npz(df: pd.DataFrame, parquet_path: Path) -> None:
    save_masks_npy(df, parquet_path)


def _try_migrate_npz_sidecars_to_npy(parquet_path: Path) -> bool:
    migrated = False
    if dims_npz_path(parquet_path).is_file() and _dims_npy_needs_rebuild(parquet_path):
        arrays = _load_dims_npz_legacy(parquet_path)
        if arrays:
            save_dims_npy_from_arrays(arrays, parquet_path)
            migrated = True
    if masks_npz_path(parquet_path).is_file():
        if _masks_npz_needs_rebuild_legacy(parquet_path):
            return migrated
        arrays = _load_masks_npz_legacy(parquet_path)
        if arrays:
            save_masks_npy_from_arrays(arrays, parquet_path)
            migrated = True
    if migrated:
        meta = load_mart_meta(parquet_path)
        if meta is not None:
            save_mart_meta(
                parquet_path=parquet_path,
                meta=MartMeta(
                    dimension_labels=meta.dimension_labels,
                    skipped_charge=meta.skipped_charge,
                    routes_without_volume=meta.routes_without_volume,
                    row_count=meta.row_count,
                    filter_options=meta.filter_options,
                    sidecar_schema_version=SIDECAR_SCHEMA_VERSION,
                ),
            )
    return migrated


def _normalize_mask_label_values(values: list[str] | np.ndarray) -> list[str]:
    normalized: list[str] = []
    seen: set[str] = set()
    for raw in values:
        text = str(raw).strip()
        if not text or text in seen:
            continue
        seen.add(text)
        normalized.append(text)
    return normalized


def _mask_column_labels_from_df(df: pd.DataFrame, column: str) -> list[str]:
    if column not in df.columns:
        return []
    return _normalize_mask_label_values(df[column].astype(str).unique().tolist())


def _merge_mask_labels_into_meta(df: pd.DataFrame, meta: MartMeta | None) -> MartMeta | None:
    if meta is None:
        return None
    updated_labels = dict(meta.dimension_labels)
    changed = False
    for column in MART_MASK_LABEL_COLUMNS:
        if column not in df.columns:
            continue
        labels = _mask_column_labels_from_df(df, column)
        if updated_labels.get(column) != labels:
            updated_labels[column] = labels
            changed = True
    if not changed:
        return meta
    return MartMeta(
        dimension_labels=updated_labels,
        skipped_charge=meta.skipped_charge,
        routes_without_volume=meta.routes_without_volume,
        row_count=meta.row_count,
        filter_options=meta.filter_options,
        sidecar_schema_version=meta.sidecar_schema_version,
    )


def distinct_mask_sidecar_labels(
    *,
    route_set_id: int,
    column: str,
) -> list[str] | None:
    """Уникальные значения mask-sidecar колонки из meta витрины."""
    if column not in MART_MASK_LABEL_COLUMNS:
        return None

    parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    if not parquet_path.is_file():
        return None

    meta = load_mart_meta(parquet_path)
    if meta is None:
        return None
    cached = meta.dimension_labels.get(column)
    if not cached:
        return None
    labels = _normalize_mask_label_values(cached)
    return labels or None


def _sidecars_complete(parquet_path: Path) -> bool:
    return (
        charge_npy_path(parquet_path).is_file()
        and volume_npy_path(parquet_path).is_file()
        and not _dims_npy_needs_rebuild(parquet_path)
        and not _masks_npy_needs_rebuild(parquet_path)
    )


def ensure_compute_sidecars(parquet_path: Path) -> bool:
    """Гарантирует charge/volume/dims/masks sidecar для витрины."""
    if _sidecars_complete(parquet_path):
        return True
    if not parquet_path.is_file():
        return False

    _try_migrate_npz_sidecars_to_npy(parquet_path)
    if _sidecars_complete(parquet_path):
        return True

    need_charge = not charge_npy_path(parquet_path).is_file()
    need_volume = not volume_npy_path(parquet_path).is_file()
    need_dims = _dims_npy_needs_rebuild(parquet_path)
    need_masks = _masks_npy_needs_rebuild(parquet_path)

    has_source = _parquet_has_sidecar_source_columns(parquet_path)
    if (need_dims or need_masks or need_charge) and not has_source:
        return False

    columns_to_read: list[str] = list(MART_COMPUTE_BASE_COLUMNS)
    if need_volume:
        columns_to_read.append("transport_volume_tons")
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
    if df.empty and (need_dims or need_masks or need_charge):
        return False

    meta = load_mart_meta(parquet_path)

    if need_charge:
        if "freight_charge_rub" not in df.columns:
            return False
        save_charge_npy(df, parquet_path)
    if need_volume:
        if "transport_volume_tons" in df.columns:
            save_volume_npy(df, parquet_path)
        elif not ensure_volume_npy(parquet_path):
            return False
    if need_dims:
        meta = _encode_mask_dims_into_df(df, meta=meta) or meta
        save_dims_npy(df, parquet_path)
    if need_masks:
        if not _mask_sidecar_columns_in_df(df):
            return False
        save_masks_npy(df, parquet_path)
        meta = _merge_mask_labels_into_meta(df, meta) or meta
    if meta is not None and (
        need_dims or need_masks or meta.sidecar_schema_version < SIDECAR_SCHEMA_VERSION
    ):
        save_mart_meta(
            parquet_path=parquet_path,
            meta=MartMeta(
                dimension_labels=meta.dimension_labels,
                skipped_charge=meta.skipped_charge,
                routes_without_volume=meta.routes_without_volume,
                row_count=meta.row_count,
                filter_options=meta.filter_options,
                sidecar_schema_version=SIDECAR_SCHEMA_VERSION,
            ),
        )
    return _sidecars_complete(parquet_path)


def load_mart_sidecar(
    parquet_path: Path,
    *,
    include_charge: bool = True,
    include_volume: bool = False,
) -> tuple[MartSidecarView, dict[str, int]]:
    """Собирает mmap-view sidecar без pandas DataFrame."""
    timings: dict[str, int] = {}
    columns: dict[str, np.ndarray] = {}

    if include_charge:
        t_charge = time.perf_counter()
        charge = load_charge_npy(parquet_path)
        if charge is None:
            charge_arr = ensure_charge_npy(parquet_path)
            if charge_arr is not None:
                charge = charge_arr
        if charge is not None:
            columns["freight_charge_rub"] = charge
        timings["charge_npy_read_ms"] = int((time.perf_counter() - t_charge) * 1000)

    if include_volume:
        t_volume = time.perf_counter()
        volume = load_volume_npy(parquet_path)
        if volume is None:
            volume = ensure_volume_npy(parquet_path)
        if volume is not None:
            columns["transport_volume_tons"] = volume
        timings["volume_npy_read_ms"] = int((time.perf_counter() - t_volume) * 1000)

    t_dims = time.perf_counter()
    columns.update(load_dims_npy_mmap(parquet_path))
    timings["dims_npy_read_ms"] = int((time.perf_counter() - t_dims) * 1000)
    timings["dims_npz_read_ms"] = timings["dims_npy_read_ms"]

    t_masks = time.perf_counter()
    columns.update(load_masks_npy_mmap(parquet_path))
    timings["masks_npy_read_ms"] = int((time.perf_counter() - t_masks) * 1000)
    timings["masks_npz_read_ms"] = timings["masks_npy_read_ms"]

    if not columns:
        return MartSidecarView(column_arrays={}), timings
    lengths = {len(value) for value in columns.values()}
    if len(lengths) != 1:
        target_len = max(lengths)
        columns = {
            key: value
            for key, value in columns.items()
            if len(value) == target_len
        }
    return MartSidecarView(column_arrays=columns), timings


def load_mart_sidecar_dataframe(
    parquet_path: Path,
    *,
    include_charge: bool = True,
    include_volume: bool = False,
) -> tuple[pd.DataFrame, dict[str, int]]:
    """Legacy: DataFrame из sidecar (медленнее, чем load_mart_sidecar)."""
    view, timings = load_mart_sidecar(
        parquet_path,
        include_charge=include_charge,
        include_volume=include_volume,
    )
    return view.to_dataframe(), timings


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
) -> tuple[MartSidecarView | pd.DataFrame | None, MartMeta | None, dict[str, int | str]]:
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

    if not _parquet_schema_is_current(path):
        timings["cache_hit"] = 0
        timings["mart_schema_stale"] = 1
        timings["parquet_read_ms"] = 0
        return None, None, timings

    if not _sidecars_complete(path) and not ensure_compute_sidecars(path):
        timings["cache_hit"] = 0
        timings["mart_sidecars_stale"] = 1
        timings["parquet_read_ms"] = 0
        return None, None, timings

    meta = load_mart_meta(path)
    t_read = time.perf_counter()

    if columns is not None and columns == list(MART_COMPUTE_BASE_COLUMNS):
        charge = load_charge_npy(path)
        if charge is None:
            charge = ensure_charge_npy(path)
        if charge is not None:
            view = MartSidecarView(column_arrays={"freight_charge_rub": charge})
            timings["charge_npy_read_ms"] = int((time.perf_counter() - t_read) * 1000)
            timings["parquet_read_ms"] = timings["charge_npy_read_ms"]
            timings["mart_read_mode"] = "charge_npy"
            timings["cache_hit"] = 1
            timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))
            return view, meta, timings

    if is_rules_light_mart_columns(columns):
        if ensure_compute_sidecars(path):
            view, sidecar_timings = load_mart_sidecar(path, include_charge=True)
            if not view.empty and "freight_charge_rub" in view:
                timings.update(sidecar_timings)
                total_read = (
                    timings.get("charge_npy_read_ms", 0)
                    + timings.get("dims_npy_read_ms", 0)
                    + timings.get("masks_npy_read_ms", 0)
                )
                timings["parquet_read_ms"] = total_read
                timings["mart_read_mode"] = "sidecar_mmap"
                timings["cache_hit"] = 1
                timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))
                return view, meta, timings
        timings["cache_hit"] = 0
        timings["mart_sidecars_stale"] = 1
        timings["parquet_read_ms"] = 0
        return None, None, timings

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
    meta = MartMeta(
        dimension_labels=dimension_labels,
        skipped_charge=skipped_charge,
        routes_without_volume=routes_without_volume,
        row_count=len(df),
        filter_options=filter_options,
        sidecar_schema_version=SIDECAR_SCHEMA_VERSION,
    )
    meta = _merge_mask_labels_into_meta(df, meta) or meta
    save_mart_meta(
        parquet_path=path,
        meta=meta,
    )
    save_charge_npy(df, path)
    save_volume_npy(df, path)
    save_dims_npy(df, path)
    save_masks_npy(df, path)
    save_route_mart_parquet(_build_slim_parquet_dataframe(df), path)
    t_write = time.perf_counter()
    timings["parquet_write_ms"] = int((t_write - t0) * 1000)
    timings["mart_cache_size_mb"] = int(path.stat().st_size / (1024 * 1024))

    removed = _cleanup_stale_parquet_files(
        cache_dir=path.parent,
        keep_path=path,
    )
    keep_stem = path.stem
    for suffix in (CHARGE_NPY_SUFFIX, VOLUME_NPY_SUFFIX, DIMS_NPZ_SUFFIX, MASKS_NPZ_SUFFIX):
        removed += _cleanup_stale_sidecar_files(
            cache_dir=path.parent,
            keep_stem=keep_stem,
            suffix=suffix,
        )
    removed += _remove_stale_sidecar_npy_files(
        cache_dir=path.parent,
        keep_stem=keep_stem,
    )
    timings["mart_cache_cleanup_removed"] = removed

    from calculations.domain.services.rule_mask_prewarm import (
        prewarm_rules_for_route_set,
    )

    timings["rule_masks_prewarmed"] = prewarm_rules_for_route_set(
        route_set_id=route_set_id,
    )
    return timings
