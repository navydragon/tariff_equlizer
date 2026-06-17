"""
Диагностика parquet-витрины и sidecar (charge/dims/masks.npz).

Пример на prod:
  export DJANGO_SETTINGS_MODULE=config.settings_prod
  python scripts/diagnose_route_mart_sidecars.py --route-set-id 2
"""
from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

import django

PROJECT_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(PROJECT_DIR))
os.chdir(PROJECT_DIR)
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
django.setup()

import pyarrow.parquet as pq

from calculations.domain.services.route_effects_loader import (
    fetch_routes_dataframe_cached_timed,
)
from calculations.domain.services.route_mart_store import (
    MART_PARQUET_REQUIRED_COLUMNS,
    MART_RULE_MASK_SIDECAR_COLUMNS,
    MASKS_NPZ_META_KEYS,
    MASKS_NPZ_SCHEMA_VERSION,
    _masks_npz_needs_rebuild,
    _parquet_schema_is_current,
    ensure_compute_sidecars,
    load_mart_sidecar_dataframe,
    masks_npz_path,
    resolve_mart_parquet_path,
)


def main() -> None:
    parser = argparse.ArgumentParser(description="Диагностика route mart sidecar.")
    parser.add_argument("--route-set-id", type=int, default=2)
    args = parser.parse_args()

    parquet = resolve_mart_parquet_path(route_set_id=args.route_set_id)
    print(f"parquet: {parquet}")
    if not parquet.is_file():
        print("ERROR: parquet не найден")
        sys.exit(1)

    cols = set(pq.ParquetFile(parquet).schema_arrow.names)
    missing = MART_PARQUET_REQUIRED_COLUMNS - cols
    print(f"schema_current: {_parquet_schema_is_current(parquet)}")
    print(f"missing_required: {missing or '-'}")

    mpath = masks_npz_path(parquet)
    if mpath.is_file():
        size_mb = round(mpath.stat().st_size / 2**20, 1)
        print(f"masks_npz exists: True size_mb: {size_mb}")
        if size_mb > 500:
            print("WARNING: masks.npz > 500 MB — вероятно U256 sidecar, нужна пересборка")
        import numpy as np

        with np.load(mpath, allow_pickle=False) as data:
            keys = {k for k in data.files if k not in MASKS_NPZ_META_KEYS}
            schema = (
                int(np.asarray(data["__schema_version__"]).reshape(-1)[0])
                if "__schema_version__" in data.files
                else None
            )
        required = {c for c in MART_RULE_MASK_SIDECAR_COLUMNS if c in cols}
        print(f"masks_npz_schema: {schema} (expected {MASKS_NPZ_SCHEMA_VERSION})")
        print(f"masks keys: {sorted(keys)}")
        print(f"missing_in_masks: {required - keys or '-'}")
        print(f"needs_rebuild: {_masks_npz_needs_rebuild(parquet)}")
    else:
        print("masks_npz exists: False")
        print(f"needs_rebuild: {_masks_npz_needs_rebuild(parquet)}")

    sample_cols = ["cargo_code_3", "cargo_code_izpod_3", "special_container_type"]
    present = [c for c in sample_cols if c in cols]
    if present:
        table = pq.read_table(parquet, columns=present)
        df = table.to_pandas()
        n = len(df)
        for column in present:
            nonempty = int((df[column].astype(str).str.strip() != "").sum())
            pct = 100.0 * nonempty / n if n else 0.0
            print(f"{column}: nonempty {nonempty}/{n} ({pct:.1f}%)")

    for attempt in (1, 2):
        t0 = time.perf_counter()
        ok = ensure_compute_sidecars(parquet)
        elapsed_ms = int((time.perf_counter() - t0) * 1000)
        print(f"ensure_compute_sidecars #{attempt}: {ok} in {elapsed_ms} ms")

    t0 = time.perf_counter()
    sidecar_df, sidecar_timings = load_mart_sidecar_dataframe(
        parquet,
        include_charge=True,
    )
    print(
        f"sidecar load: {sidecar_timings} "
        f"total={int((time.perf_counter() - t0) * 1000)} ms "
        f"rows={len(sidecar_df)}",
    )

    t0 = time.perf_counter()
    _df, _meta, load_timings = fetch_routes_dataframe_cached_timed(args.route_set_id)
    print(
        f"fetch_routes: wall={int((time.perf_counter() - t0) * 1000)} ms "
        f"timings={load_timings}",
    )


if __name__ == "__main__":
    main()
