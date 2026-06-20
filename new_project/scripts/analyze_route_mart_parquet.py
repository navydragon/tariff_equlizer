"""
Анализ parquet-витрины маршрутов: размер, колонки, типы, рекомендации по сжатию.

Пример:
  python scripts/analyze_route_mart_parquet.py --route-set-id 3 \\
      --output reports/route_mart_parquet_analysis.md
"""
from __future__ import annotations

import argparse
import os
import sys
from dataclasses import dataclass
from datetime import date
from pathlib import Path

import django

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import numpy as np
import pandas as pd
import pyarrow.parquet as pq

from calculations.domain.services.route_mart_store import (
    CHARGE_NPY_SUFFIX,
    DIMS_NPZ_SUFFIX,
    MASKS_NPZ_SUFFIX,
    META_SUFFIX,
    load_mart_meta,
    load_route_mart_parquet,
    resolve_mart_parquet_path,
)
from calculations.domain.services.scenario_effects_compact import _DIMENSION_COLUMNS

# --- Классификация колонок (по коду calculations) ---

KEEP_PARQUET_ONLY = frozenset(
    {
        "transport_volume_tons",
        "cargo_group_code",
    },
)

KEEP_SIDECAR_OR_PARQUET = frozenset(
    {
        "freight_charge_rub",
        "wagon_kind_id",
        "shipment_type_id",
        "message_type_id",
        "shipper_id",
        "distance_belt",
        "distance_belt_midpoint_km",
        "special_container_type",
        "cargo_code_3",
        "cargo_code_izpod_3",
        "cargo_group_izpod",
    },
)

REDUNDANT = frozenset(
    {
        "id",
        "cargo_id",
        "origin_station_id",
        "destination_station_id",
        "distance_loaded_km",
        "direction_raw",
        "shipper_holding",
        "cargo_group",
        "cargo_code",
        "direction",
        "wagon_kind",
        "transport_type",
        "shipment_category",
        "park_type",
        "holding",
        "origin_railroad_code",
        "destination_railroad_code",
    },
)

_DIM_COLS = frozenset(
    {f"dim_{c}" for c in _DIMENSION_COLUMNS}
    | {"dim_origin_railroad", "dim_destination_railroad"}
)


@dataclass
class ColumnStats:
    name: str
    arrow_dtype: str
    pandas_dtype: str
    memory_bytes: int
    nunique: int
    null_pct: float
    min_val: str
    max_val: str
    max_str_len: int | None
    category: str
    recommended_dtype: str
    recommended_bytes: int


def _file_size_mb(path: Path) -> float:
    if not path.is_file():
        return 0.0
    return path.stat().st_size / (1024 * 1024)


def _classify_column(name: str) -> str:
    if name in KEEP_PARQUET_ONLY:
        return "KEEP (parquet-only)"
    if name in KEEP_SIDECAR_OR_PARQUET:
        return "KEEP (sidecar)"
    if name in REDUNDANT:
        return "REDUNDANT"
    if name in _DIM_COLS:
        return "SIDECAR_ONLY (dims.npz)"
    return "UNKNOWN"


def _recommend_dtype(
    name: str,
    series: pd.Series,
    nunique: int,
    max_num: float | None,
    max_str_len: int | None,
) -> tuple[str, int]:
    n = len(series)
    if n == 0:
        return "empty", 0

    if name == "freight_charge_rub":
        return "float64", n * 8

    if name == "transport_volume_tons":
        return "float32", n * 4

    if name == "cargo_group_code":
        if max_num is not None and max_num <= 255:
            return "uint8", n * 1
        if max_num is not None and max_num <= 65535:
            return "uint16", n * 2
        return "uint16", n * 2

    if name in {"wagon_kind_id", "shipment_type_id", "message_type_id"}:
        if max_num is not None and max_num <= 65535:
            return "uint16", n * 2
        return "uint32", n * 4

    if name == "shipper_id":
        if max_num is not None and max_num <= 65535:
            return "uint16", n * 2
        if max_num is not None and max_num <= 4294967295:
            return "uint32", n * 4
        return "int64", n * 8

    if name == "distance_belt_midpoint_km":
        if max_num is not None and max_num <= 65535:
            return "uint16", n * 2
        return "uint32", n * 4

    if name in {"cargo_code_3", "cargo_code_izpod_3"}:
        width = max(4, (max_str_len or 0) + 1)
        return f"U{width}", n * width

    if name == "distance_belt":
        width = min(32, max(8, (max_str_len or 0) + 1))
        return f"U{width}", n * width

    if name in {"cargo_group_izpod", "special_container_type"}:
        width = min(64, max(8, (max_str_len or 0) + 1))
        return f"U{width}", n * width

    if name.startswith("dim_"):
        if nunique <= 255:
            return "uint8", n * 1
        if nunique <= 65535:
            return "uint16", n * 2
        return "int32", n * 4

    if name == "cargo_code":
        return "U6", n * 6

    if pd.api.types.is_numeric_dtype(series):
        if max_num is not None and max_num <= 255 and nunique <= 256:
            return "uint8", n * 1
        if max_num is not None and max_num <= 65535:
            return "uint16", n * 2
        if pd.api.types.is_integer_dtype(series):
            return "int32", n * 4
        return "float32", n * 4

    if max_str_len is not None:
        width = min(64, max(8, max_str_len + 1))
        return f"U{width}", n * width

    return "object", int(series.memory_usage(deep=True))


def _analyze_column(
    name: str,
    series: pd.Series,
    arrow_dtype: str,
    memory_bytes: int,
) -> ColumnStats:
    null_pct = float(series.isna().mean() * 100)
    nunique = int(series.nunique(dropna=True))

    max_num: float | None = None
    max_str_len: int | None = None
    min_val = ""
    max_val = ""

    if pd.api.types.is_numeric_dtype(series):
        valid = series.dropna()
        if len(valid):
            max_num = float(valid.max())
            min_val = str(valid.min())
            max_val = str(valid.max())
    else:
        as_str = series.dropna().astype(str)
        if len(as_str):
            max_str_len = int(as_str.str.len().max())
            min_val = as_str.min()
            max_val = as_str.max()

    rec_dtype, rec_bytes = _recommend_dtype(
        name, series, nunique, max_num, max_str_len,
    )

    return ColumnStats(
        name=name,
        arrow_dtype=arrow_dtype,
        pandas_dtype=str(series.dtype),
        memory_bytes=memory_bytes,
        nunique=nunique,
        null_pct=null_pct,
        min_val=min_val,
        max_val=max_val,
        max_str_len=max_str_len,
        category=_classify_column(name),
        recommended_dtype=rec_dtype,
        recommended_bytes=rec_bytes,
    )


def _sidecar_paths(parquet_path: Path) -> dict[str, Path]:
    stem = parquet_path.stem
    parent = parquet_path.parent
    return {
        "parquet": parquet_path,
        "meta": parquet_path.with_suffix(parquet_path.suffix + META_SUFFIX),
        "charge": parent / (stem + CHARGE_NPY_SUFFIX),
        "dims": parent / (stem + DIMS_NPZ_SUFFIX),
        "masks": parent / (stem + MASKS_NPZ_SUFFIX),
    }


def analyze_route_mart(*, route_set_id: int) -> dict:
    parquet_path = resolve_mart_parquet_path(route_set_id=route_set_id)
    if not parquet_path.is_file():
        raise FileNotFoundError(f"Parquet не найден: {parquet_path}")

    paths = _sidecar_paths(parquet_path)
    pf = pq.ParquetFile(parquet_path)
    arrow_schema = {f.name: str(f.type) for f in pf.schema_arrow}
    row_count = pf.metadata.num_rows if pf.metadata else 0

    meta = load_mart_meta(parquet_path)
    if meta and meta.row_count:
        row_count = meta.row_count

    file_sizes = {key: _file_size_mb(path) for key, path in paths.items()}
    file_sizes["total_mb"] = sum(file_sizes.values())

    df = load_route_mart_parquet(parquet_path)
    mem = df.memory_usage(deep=True)
    total_memory = int(mem.sum())

    column_stats: list[ColumnStats] = []
    for col in df.columns:
        column_stats.append(
            _analyze_column(
                col,
                df[col],
                arrow_schema.get(col, "?"),
                int(mem[col]),
            ),
        )

    by_category: dict[str, list[ColumnStats]] = {}
    for cs in column_stats:
        by_category.setdefault(cs.category, []).append(cs)

    redundant_memory = sum(
        cs.memory_bytes for cs in column_stats if cs.category == "REDUNDANT"
    )
    sidecar_only_memory = sum(
        cs.memory_bytes
        for cs in column_stats
        if cs.category == "SIDECAR_ONLY (dims.npz)"
    )
    keep_memory = sum(
        cs.memory_bytes
        for cs in column_stats
        if cs.category.startswith("KEEP")
    )

    slim_keep = [
        cs for cs in column_stats if cs.category.startswith("KEEP")
    ]
    slim_recommended = sum(cs.recommended_bytes for cs in slim_keep)
    slim_current = sum(cs.memory_bytes for cs in slim_keep)
    slim_savings = slim_current - slim_recommended

    theoretical_slim = slim_recommended
    theoretical_savings = total_memory - theoretical_slim - redundant_memory - sidecar_only_memory

    masks_info: dict = {}
    if paths["masks"].is_file():
        try:
            with np.load(paths["masks"], allow_pickle=False) as data:
                masks_info = {
                    "keys": sorted(k for k in data.files if not k.startswith("__")),
                    "schema_version": (
                        int(np.asarray(data["__schema_version__"]).reshape(-1)[0])
                        if "__schema_version__" in data.files
                        else None
                    ),
                    "dtypes": {
                        k: str(data[k].dtype)
                        for k in data.files
                        if not k.startswith("__")
                    },
                }
        except OSError as exc:
            masks_info = {"error": str(exc)}

    return {
        "route_set_id": route_set_id,
        "parquet_path": str(parquet_path),
        "row_count": row_count,
        "column_count": len(df.columns),
        "file_sizes_mb": file_sizes,
        "total_memory_mb": total_memory / (1024 * 1024),
        "bytes_per_row": total_memory / row_count if row_count else 0,
        "column_stats": column_stats,
        "by_category": by_category,
        "redundant_memory_mb": redundant_memory / (1024 * 1024),
        "sidecar_only_memory_mb": sidecar_only_memory / (1024 * 1024),
        "keep_memory_mb": keep_memory / (1024 * 1024),
        "slim_current_mb": slim_current / (1024 * 1024),
        "slim_recommended_mb": slim_recommended / (1024 * 1024),
        "slim_savings_mb": slim_savings / (1024 * 1024),
        "theoretical_parquet_mb": theoretical_slim / (1024 * 1024),
        "theoretical_total_savings_mb": (
            redundant_memory + sidecar_only_memory + slim_savings
        ) / (1024 * 1024),
        "meta": meta,
        "masks_info": masks_info,
    }


def _fmt_mb(value: float) -> str:
    return f"{value:.2f}"


def render_report(data: dict) -> str:
    today = date.today().isoformat()
    lines: list[str] = [
        f"# Анализ parquet-витрины маршрутов ({today})",
        "",
        f"**RouteSet id:** {data['route_set_id']}  ",
        f"**Файл:** `{data['parquet_path']}`  ",
        f"**Строк:** {data['row_count']:,}  ",
        f"**Колонок в parquet:** {data['column_count']}",
        "",
        "## 1. Summary — размеры файлов",
        "",
        "| Файл | Размер, МБ |",
        "|------|------------|",
    ]

    fs = data["file_sizes_mb"]
    for key in ("parquet", "charge", "dims", "masks", "meta", "total_mb"):
        label = {
            "parquet": "parquet",
            "charge": "charge.npy",
            "dims": "dims.npz",
            "masks": "masks.npz",
            "meta": "meta.json",
            "total_mb": "**Итого**",
        }[key]
        lines.append(f"| {label} | {_fmt_mb(fs[key])} |")

    lines.extend(
        [
            "",
            f"- In-memory DataFrame: **{_fmt_mb(data['total_memory_mb'])} МБ**",
            f"- Байт на строку (in-memory): **{data['bytes_per_row']:.1f}**",
            "",
            "## 2. Column inventory",
            "",
            "| Колонка | Arrow dtype | Pandas dtype | Memory МБ | nunique | null% | min | max |",
            "|---------|-------------|--------------|-----------|---------|-------|-----|-----|",
        ],
    )

    for cs in sorted(data["column_stats"], key=lambda x: -x.memory_bytes):
        mem_mb = cs.memory_bytes / (1024 * 1024)
        lines.append(
            f"| `{cs.name}` | {cs.arrow_dtype} | {cs.pandas_dtype} | "
            f"{mem_mb:.2f} | {cs.nunique:,} | {cs.null_pct:.1f} | "
            f"{cs.min_val[:40]} | {cs.max_val[:40]} |",
        )

    lines.extend(["", "## 3. Redundancy table", ""])
    for category in (
        "KEEP (parquet-only)",
        "KEEP (sidecar)",
        "SIDECAR_ONLY (dims.npz)",
        "REDUNDANT",
        "UNKNOWN",
    ):
        cols = data["by_category"].get(category, [])
        if not cols:
            continue
        mem = sum(c.memory_bytes for c in cols) / (1024 * 1024)
        names = ", ".join(f"`{c.name}`" for c in cols)
        lines.append(f"### {category} ({_fmt_mb(mem)} МБ)")
        lines.append("")
        lines.append(names)
        lines.append("")

    lines.extend(
        [
            "**Итого избыточно в parquet:** "
            f"REDUNDANT {_fmt_mb(data['redundant_memory_mb'])} МБ + "
            f"SIDECAR_ONLY {_fmt_mb(data['sidecar_only_memory_mb'])} МБ = "
            f"**{_fmt_mb(data['redundant_memory_mb'] + data['sidecar_only_memory_mb'])} МБ**",
            "",
            "**Минимальный theoretical slim-parquet:** "
            "`transport_volume_tons`, `cargo_group_code` "
            "(+ опционально `freight_charge_rub` как fallback без charge.npy).",
            "",
            "## 4. Type recommendations (KEEP-колонки)",
            "",
            "| Колонка | Текущий | min | max | nunique | Рекомендация | Экономия МБ |",
            "|---------|---------|-----|-----|---------|--------------|-------------|",
        ],
    )

    for cs in sorted(data["column_stats"], key=lambda x: x.name):
        if not cs.category.startswith("KEEP"):
            continue
        saving = (cs.memory_bytes - cs.recommended_bytes) / (1024 * 1024)
        lines.append(
            f"| `{cs.name}` | {cs.pandas_dtype} | {cs.min_val[:30]} | "
            f"{cs.max_val[:30]} | {cs.nunique:,} | {cs.recommended_dtype} | "
            f"{saving:.2f} |",
        )

    lines.extend(
        [
            "",
            "## 5. Estimated savings (теоретически, без внедрения)",
            "",
            f"| Метрика | МБ |",
            f"|---------|-----|",
            f"| Память REDUNDANT колонок | {_fmt_mb(data['redundant_memory_mb'])} |",
            f"| Память SIDECAR_ONLY (dim_*) | {_fmt_mb(data['sidecar_only_memory_mb'])} |",
            f"| Downcast KEEP-колонок | {_fmt_mb(data['slim_savings_mb'])} |",
            f"| **Суммарная экономия in-memory** | "
            f"**{_fmt_mb(data['theoretical_total_savings_mb'])}** |",
            f"| Theoretical slim-parquet in-memory | "
            f"{_fmt_mb(data['theoretical_parquet_mb'])} |",
            "",
            "Экстраполяция на диск (snappy): ориентир **30–50%** от in-memory "
            "для строковых колонок; числовые сжимаются слабее.",
            "",
        ],
    )

    mi = data.get("masks_info") or {}
    if mi:
        lines.extend(["## 6. Sidecar masks.npz", ""])
        if "error" in mi:
            lines.append(f"Ошибка чтения: {mi['error']}")
        else:
            lines.append(f"- schema_version: {mi.get('schema_version')}")
            lines.append(f"- keys: {', '.join(mi.get('keys', []))}")
            if mi.get("dtypes"):
                lines.append("- dtypes:")
                for k, v in mi["dtypes"].items():
                    lines.append(f"  - `{k}`: {v}")
            if fs.get("masks", 0) > 500:
                lines.append(
                    f"\n**WARNING:** masks.npz = {_fmt_mb(fs['masks'])} МБ — "
                    "вероятно устаревшая схема (U256). "
                    "Пересборка: `refresh_deploy_caches --clear-only` затем `--warm-only`.",
                )

    lines.extend(
        [
            "",
            "## Примечания",
            "",
            "- Hot-path расчёта (`resolve_light_mart_columns`) читает sidecar, не parquet.",
            "- `transport_volume_tons` не имеет sidecar — deferred compute читает full parquet.",
            "- `cargo_group_code` нужен как fallback для matching правил.",
            "",
        ],
    )

    return "\n".join(lines)


def main() -> None:
    parser = argparse.ArgumentParser(description="Анализ parquet-витрины route mart.")
    parser.add_argument("--route-set-id", type=int, default=3)
    parser.add_argument(
        "--output",
        type=str,
        default="",
        help="Путь к markdown-отчёту (по умолчанию reports/route_mart_parquet_analysis_{date}.md)",
    )
    args = parser.parse_args()

    output = args.output
    if not output:
        output = f"reports/route_mart_parquet_analysis_{date.today().isoformat()}.md"

    print(f"Analyzing route_set_id={args.route_set_id}...")
    data = analyze_route_mart(route_set_id=args.route_set_id)
    report = render_report(data)

    out_path = Path(output)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(report, encoding="utf-8")

    print(f"Rows: {data['row_count']:,}")
    print(f"Parquet: {_fmt_mb(data['file_sizes_mb']['parquet'])} MB")
    print(f"Total bundle: {_fmt_mb(data['file_sizes_mb']['total_mb'])} MB")
    print(f"In-memory: {_fmt_mb(data['total_memory_mb'])} MB")
    print(f"Report: {out_path}")


if __name__ == "__main__":
    main()
