from __future__ import annotations

import json
import os
import shutil
import time
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
from django.conf import settings

from calculations.domain.services.scenario_effects_cache import CompactRouteEffects
from calculations.domain.services.scenario_effects_compact import _DIMENSION_COLUMNS
from calculations.domain.services.scenario_effects_formatting import GlobalTotals
from calculations.domain.services.scenario_effects_preaggregate import (
    DensePairBucket,
    DenseTripleBucket,
    EffectsPreAggregate,
    SingleBucket,
    SparsePairBucket,
    SparseTripleBucket,
)

NPZ_FILENAME = "arrays.npz"
PREAGG_FILENAME = "preagg.npz"
RULE_BY_YEAR_FILENAME = "rule_by_year.npy"
METADATA_FILENAME = "metadata.json"


@dataclass
class ScenarioComputeBundle:
    compact: CompactRouteEffects | None
    preaggregate: EffectsPreAggregate | None
    global_totals: GlobalTotals
    filter_options: dict[str, list[str]]
    skipped_charge: int
    routes_without_volume: int


def scenario_compute_cache_root() -> Path:
    configured = getattr(settings, "SCENARIO_COMPUTE_CACHE_DIR", None)
    if configured:
        return Path(configured)
    return Path(settings.BASE_DIR) / "cache" / "scenario_compute"


def scenario_compute_dir(*, scenario_id: int, data_version: str) -> Path:
    return scenario_compute_cache_root() / str(scenario_id) / data_version


def _global_totals_to_json(totals: GlobalTotals) -> dict:
    return {
        "baseline_total": str(totals.baseline_total),
        "base_by_year": {str(k): str(v) for k, v in totals.base_by_year.items()},
        "rules_by_year": {str(k): str(v) for k, v in totals.rules_by_year.items()},
        "charge_by_year": {str(k): str(v) for k, v in totals.charge_by_year.items()},
    }


def _global_totals_from_json(payload: dict) -> GlobalTotals:
    totals = GlobalTotals()
    totals.baseline_total = Decimal(payload.get("baseline_total", "0"))
    for key, value in (payload.get("base_by_year") or {}).items():
        totals.base_by_year[int(key)] = Decimal(value)
    for key, value in (payload.get("rules_by_year") or {}).items():
        totals.rules_by_year[int(key)] = Decimal(value)
    for key, value in (payload.get("charge_by_year") or {}).items():
        totals.charge_by_year[int(key)] = Decimal(value)
    return totals


def _pair_key(outer: str, inner: str) -> str:
    return f"{outer}__{inner}"


def _triple_key(a: str, b: str, c: str) -> str:
    return f"{a}__{b}__{c}"


def _preaggregate_arrays_for_store(preagg: EffectsPreAggregate) -> tuple[dict[str, np.ndarray], dict]:
    arrays: dict[str, np.ndarray] = {}
    layout: dict[str, list] = {
        "singles": [],
        "pairs_dense": [],
        "pairs_sparse": [],
        "triples_dense": [],
        "triples_sparse": [],
    }

    for dim, bucket in preagg.singles.items():
        key = _pair_key("single", dim)
        layout["singles"].append(dim)
        arrays[f"{key}_base"] = bucket.base.astype(np.float32, copy=False)
        arrays[f"{key}_rules"] = bucket.rules.astype(np.float32, copy=False)
        arrays[f"{key}_charge"] = bucket.charge.astype(np.float32, copy=False)
        arrays[f"{key}_volume"] = bucket.volume.astype(np.float32, copy=False)

    for (outer, inner), bucket in preagg.pairs_dense.items():
        pk = _pair_key(outer, inner)
        layout["pairs_dense"].append([outer, inner])
        arrays[f"pd_{pk}_base"] = bucket.base.astype(np.float32, copy=False)
        arrays[f"pd_{pk}_rules"] = bucket.rules.astype(np.float32, copy=False)
        arrays[f"pd_{pk}_charge"] = bucket.charge.astype(np.float32, copy=False)
        arrays[f"pd_{pk}_volume"] = bucket.volume.astype(np.float32, copy=False)

    for (outer, inner), bucket in preagg.pairs_sparse.items():
        pk = _pair_key(outer, inner)
        layout["pairs_sparse"].append([outer, inner, bucket.n_outer, bucket.n_inner])
        arrays[f"ps_{pk}_outer_idx"] = bucket.outer_idx.astype(np.int32, copy=False)
        arrays[f"ps_{pk}_inner_idx"] = bucket.inner_idx.astype(np.int32, copy=False)
        arrays[f"ps_{pk}_base"] = bucket.base.astype(np.float32, copy=False)
        arrays[f"ps_{pk}_rules"] = bucket.rules.astype(np.float32, copy=False)
        arrays[f"ps_{pk}_charge"] = bucket.charge.astype(np.float32, copy=False)
        arrays[f"ps_{pk}_volume"] = bucket.volume.astype(np.float32, copy=False)

    for (a, b, c), bucket in preagg.triples_dense.items():
        tk = _triple_key(a, b, c)
        layout["triples_dense"].append([a, b, c, list(bucket.shape)])
        arrays[f"td_{tk}_base"] = bucket.base.astype(np.float32, copy=False)
        arrays[f"td_{tk}_rules"] = bucket.rules.astype(np.float32, copy=False)
        arrays[f"td_{tk}_charge"] = bucket.charge.astype(np.float32, copy=False)
        arrays[f"td_{tk}_volume"] = bucket.volume.astype(np.float32, copy=False)

    for (a, b, c), bucket in preagg.triples_sparse.items():
        tk = _triple_key(a, b, c)
        layout["triples_sparse"].append([a, b, c, list(bucket.shape)])
        arrays[f"ts_{tk}_flat_idx"] = bucket.flat_idx.astype(np.int64, copy=False)
        arrays[f"ts_{tk}_base"] = bucket.base.astype(np.float32, copy=False)
        arrays[f"ts_{tk}_rules"] = bucket.rules.astype(np.float32, copy=False)
        arrays[f"ts_{tk}_charge"] = bucket.charge.astype(np.float32, copy=False)
        arrays[f"ts_{tk}_volume"] = bucket.volume.astype(np.float32, copy=False)

    return arrays, layout


def _load_preaggregate_from_npz(
    data,
    *,
    years: list[int],
    dimension_labels: dict[str, list[str]],
    layout: dict,
) -> EffectsPreAggregate:
    singles: dict[str, SingleBucket] = {}
    for dim in layout.get("singles") or []:
        key = _pair_key("single", dim)
        singles[dim] = SingleBucket(
            base=data[f"{key}_base"],
            rules=data[f"{key}_rules"],
            charge=data[f"{key}_charge"],
            volume=data[f"{key}_volume"],
        )

    pairs_dense: dict[tuple[str, str], DensePairBucket] = {}
    for outer, inner in layout.get("pairs_dense") or []:
        pk = _pair_key(outer, inner)
        n_outer = len(dimension_labels.get(outer, []))
        n_inner = len(dimension_labels.get(inner, []))
        pairs_dense[(outer, inner)] = DensePairBucket(
            outer_dim=outer,
            inner_dim=inner,
            n_outer=n_outer,
            n_inner=n_inner,
            base=data[f"pd_{pk}_base"],
            rules=data[f"pd_{pk}_rules"],
            charge=data[f"pd_{pk}_charge"],
            volume=data[f"pd_{pk}_volume"],
        )

    pairs_sparse: dict[tuple[str, str], SparsePairBucket] = {}
    for entry in layout.get("pairs_sparse") or []:
        outer, inner, n_outer, n_inner = entry[0], entry[1], int(entry[2]), int(entry[3])
        pk = _pair_key(outer, inner)
        pairs_sparse[(outer, inner)] = SparsePairBucket(
            outer_dim=outer,
            inner_dim=inner,
            n_outer=n_outer,
            n_inner=n_inner,
            outer_idx=data[f"ps_{pk}_outer_idx"],
            inner_idx=data[f"ps_{pk}_inner_idx"],
            base=data[f"ps_{pk}_base"],
            rules=data[f"ps_{pk}_rules"],
            charge=data[f"ps_{pk}_charge"],
            volume=data[f"ps_{pk}_volume"],
        )

    triples_dense: dict[tuple[str, str, str], DenseTripleBucket] = {}
    for entry in layout.get("triples_dense") or []:
        a, b, c = entry[0], entry[1], entry[2]
        shape = tuple(int(x) for x in entry[3])
        tk = _triple_key(a, b, c)
        triples_dense[(a, b, c)] = DenseTripleBucket(
            dim_a=a,
            dim_b=b,
            dim_c=c,
            shape=shape,
            base=data[f"td_{tk}_base"],
            rules=data[f"td_{tk}_rules"],
            charge=data[f"td_{tk}_charge"],
            volume=data[f"td_{tk}_volume"],
        )

    triples_sparse: dict[tuple[str, str, str], SparseTripleBucket] = {}
    for entry in layout.get("triples_sparse") or []:
        a, b, c = entry[0], entry[1], entry[2]
        shape = tuple(int(x) for x in entry[3])
        tk = _triple_key(a, b, c)
        triples_sparse[(a, b, c)] = SparseTripleBucket(
            dim_a=a,
            dim_b=b,
            dim_c=c,
            shape=shape,
            flat_idx=data[f"ts_{tk}_flat_idx"],
            base=data[f"ts_{tk}_base"],
            rules=data[f"ts_{tk}_rules"],
            charge=data[f"ts_{tk}_charge"],
            volume=data[f"ts_{tk}_volume"],
        )

    return EffectsPreAggregate(
        years=years,
        dimension_labels=dimension_labels,
        singles=singles,
        pairs_dense=pairs_dense,
        pairs_sparse=pairs_sparse,
        triples_dense=triples_dense,
        triples_sparse=triples_sparse,
    )


def _compact_arrays_for_store(compact: CompactRouteEffects) -> dict[str, np.ndarray]:
    arrays: dict[str, np.ndarray] = {
        "baseline_rub": compact.baseline_rub.astype(np.float32, copy=False),
        "volume_tons": compact.volume_tons.astype(np.float32, copy=False),
        "base_by_year": compact.base_by_year.astype(np.float32, copy=False),
        "rules_by_year": compact.rules_by_year.astype(np.float32, copy=False),
        "charge_by_year": compact.charge_by_year.astype(np.float32, copy=False),
    }
    for column in _DIMENSION_COLUMNS:
        arrays[f"dim_{column}"] = compact.dimensions[column].astype(np.int32, copy=False)
    return arrays


def _atomic_replace(tmp_path: Path, final_path: Path, *, max_attempts: int = 12) -> None:
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


def _save_rule_by_year(path: Path, rule_by_year: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_base = path.with_name(path.stem + ".tmp")
    np.save(tmp_base, rule_by_year.astype(np.float32, copy=False))
    _atomic_replace(Path(f"{tmp_base}.npy"), path)


def _load_rule_by_year(cache_dir: Path, data) -> np.ndarray | None:
    sidecar = cache_dir / RULE_BY_YEAR_FILENAME
    if sidecar.is_file():
        loaded = np.load(sidecar, mmap_mode="r")
        return np.asarray(loaded, dtype=np.float32)

    if data is not None and "rule_by_year" in data.files:
        return data["rule_by_year"].astype(np.float32, copy=False)
    return None


def _write_metadata(cache_dir: Path, metadata: dict) -> None:
    meta_path = cache_dir / METADATA_FILENAME
    tmp_meta = cache_dir / (METADATA_FILENAME + ".tmp")
    tmp_meta.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    _atomic_replace(tmp_meta, meta_path)


def _remove_compact_sidecars(
    cache_dir: Path,
    *,
    scenario_id: int | None = None,
    data_version: str | None = None,
) -> None:
    skip_npz = False
    if scenario_id is not None and data_version is not None:
        from calculations.domain.services.scenario_effects_deferred import (
            is_deferred_running,
        )

        skip_npz = is_deferred_running(scenario_id, data_version)

    for path in (
        cache_dir / NPZ_FILENAME,
        cache_dir / PREAGG_FILENAME,
        cache_dir / RULE_BY_YEAR_FILENAME,
    ):
        if path.name == NPZ_FILENAME and skip_npz:
            continue
        if path.is_file():
            path.unlink()


def save_scenario_compute_kpi_only(
    *,
    scenario_id: int,
    data_version: str,
    years: list[int],
    global_totals: GlobalTotals,
    filter_options: dict[str, list[str]],
    skipped_charge: int,
    routes_without_volume: int,
) -> Path:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _remove_compact_sidecars(
        cache_dir,
        scenario_id=scenario_id,
        data_version=data_version,
    )

    metadata = {
        "kpi_only": True,
        "years": years,
        "filter_options": filter_options,
        "global_totals": _global_totals_to_json(global_totals),
        "skipped_charge": skipped_charge,
        "routes_without_volume": routes_without_volume,
    }
    _write_metadata(cache_dir, metadata)
    from calculations.domain.services.scenario_effects_cache import (
        set_scenario_effects_revision,
    )

    set_scenario_effects_revision(
        scenario_id=scenario_id,
        data_version=data_version,
    )
    return cache_dir


def save_scenario_compute_preaggregate(
    *,
    scenario_id: int,
    data_version: str,
    years: list[int],
    preaggregate: EffectsPreAggregate,
    global_totals: GlobalTotals,
    filter_options: dict[str, list[str]],
    skipped_charge: int,
    routes_without_volume: int,
) -> Path:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    cache_dir.mkdir(parents=True, exist_ok=True)
    _remove_compact_sidecars(
        cache_dir,
        scenario_id=scenario_id,
        data_version=data_version,
    )

    arrays, layout = _preaggregate_arrays_for_store(preaggregate)
    tmp_path = cache_dir / "preagg.write.npz"
    with open(tmp_path, "wb") as handle:
        np.savez(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    _atomic_replace(tmp_path, cache_dir / PREAGG_FILENAME)

    metadata = {
        "kpi_only": False,
        "preaggregate": True,
        "include_rule_breakdown": False,
        "years": years,
        "dimension_labels": preaggregate.dimension_labels,
        "preaggregate_layout": layout,
        "filter_options": filter_options,
        "global_totals": _global_totals_to_json(global_totals),
        "skipped_charge": skipped_charge,
        "routes_without_volume": routes_without_volume,
    }
    _write_metadata(cache_dir, metadata)
    from calculations.domain.services.scenario_effects_cache import (
        set_scenario_effects_revision,
    )

    set_scenario_effects_revision(
        scenario_id=scenario_id,
        data_version=data_version,
    )
    return cache_dir


def purge_stale_scenario_compute(
    *,
    scenario_id: int,
    keep_data_version: str,
) -> int:
    scenario_dir = scenario_compute_cache_root() / str(scenario_id)
    if not scenario_dir.is_dir():
        return 0

    removed = 0
    for child in scenario_dir.iterdir():
        if not child.is_dir() or child.name == keep_data_version:
            continue
        shutil.rmtree(child, ignore_errors=True)
        removed += 1
    return removed


def save_scenario_compute(
    *,
    scenario_id: int,
    data_version: str,
    bundle: ScenarioComputeBundle,
) -> Path:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    cache_dir.mkdir(parents=True, exist_ok=True)

    compact = bundle.compact
    if compact is None:
        raise ValueError("save_scenario_compute requires a compact bundle")
    arrays = _compact_arrays_for_store(compact)

    tmp_path = cache_dir / "arrays.write.npz"
    with open(tmp_path, "wb") as handle:
        np.savez(handle, **arrays)
        handle.flush()
        os.fsync(handle.fileno())
    _atomic_replace(tmp_path, cache_dir / NPZ_FILENAME)

    rule_by_year_path = cache_dir / RULE_BY_YEAR_FILENAME
    if compact.rule_by_year is not None:
        _save_rule_by_year(rule_by_year_path, compact.rule_by_year)
    elif rule_by_year_path.is_file():
        rule_by_year_path.unlink()

    include_rule_breakdown = compact.rule_by_year is not None
    metadata = {
        "kpi_only": False,
        "include_rule_breakdown": include_rule_breakdown,
        "years": compact.years,
        "dimension_labels": compact.dimension_labels,
        "rule_meta": [[rule_id, name] for rule_id, name in compact.rule_meta],
        "filter_options": bundle.filter_options,
        "global_totals": _global_totals_to_json(bundle.global_totals),
        "skipped_charge": bundle.skipped_charge,
        "routes_without_volume": bundle.routes_without_volume,
    }
    _write_metadata(cache_dir, metadata)
    from calculations.domain.services.scenario_effects_cache import (
        set_scenario_effects_revision,
    )

    set_scenario_effects_revision(
        scenario_id=scenario_id,
        data_version=data_version,
    )
    return cache_dir


def is_scenario_compact_on_disk(*, scenario_id: int, data_version: str) -> bool:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    meta_path = cache_dir / METADATA_FILENAME
    if not meta_path.is_file():
        return False
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("kpi_only"):
        return False
    if metadata.get("preaggregate"):
        return (cache_dir / PREAGG_FILENAME).is_file()
    return (cache_dir / NPZ_FILENAME).is_file()


def is_scenario_preaggregate_on_disk(*, scenario_id: int, data_version: str) -> bool:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    meta_path = cache_dir / METADATA_FILENAME
    if not meta_path.is_file():
        return False
    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    return bool(metadata.get("preaggregate")) and (cache_dir / PREAGG_FILENAME).is_file()


def _bundle_from_metadata(
    metadata: dict,
    *,
    compact: CompactRouteEffects | None = None,
    preaggregate: EffectsPreAggregate | None = None,
) -> ScenarioComputeBundle:
    return ScenarioComputeBundle(
        compact=compact,
        preaggregate=preaggregate,
        global_totals=_global_totals_from_json(metadata["global_totals"]),
        filter_options=metadata.get("filter_options") or {},
        skipped_charge=int(metadata.get("skipped_charge", 0)),
        routes_without_volume=int(metadata.get("routes_without_volume", 0)),
    )


def try_load_scenario_compute(
    *,
    scenario_id: int,
    data_version: str,
) -> ScenarioComputeBundle | None:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    npz_path = cache_dir / NPZ_FILENAME
    meta_path = cache_dir / METADATA_FILENAME
    if not meta_path.is_file():
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("kpi_only"):
        return _bundle_from_metadata(metadata)

    if metadata.get("preaggregate"):
        preagg_path = cache_dir / PREAGG_FILENAME
        if not preagg_path.is_file():
            return None
        with np.load(preagg_path, allow_pickle=False) as data:
            preaggregate = _load_preaggregate_from_npz(
                data,
                years=[int(year) for year in metadata["years"]],
                dimension_labels=metadata.get("dimension_labels") or {},
                layout=metadata.get("preaggregate_layout") or {},
            )
        return _bundle_from_metadata(metadata, preaggregate=preaggregate)

    if not npz_path.is_file():
        return None

    with np.load(npz_path, allow_pickle=False) as data:
        rule_by_year = _load_rule_by_year(cache_dir, data)
        dimensions = {
            column: data[f"dim_{column}"].astype(np.int32, copy=False)
            for column in _DIMENSION_COLUMNS
        }
        compact = CompactRouteEffects(
            years=[int(year) for year in metadata["years"]],
            dimensions=dimensions,
            dimension_labels=metadata.get("dimension_labels") or {},
            baseline_rub=data["baseline_rub"],
            volume_tons=data["volume_tons"],
            base_by_year=data["base_by_year"],
            rules_by_year=data["rules_by_year"],
            charge_by_year=data["charge_by_year"],
            rule_meta=[(int(item[0]), str(item[1])) for item in metadata.get("rule_meta", [])],
            rule_by_year=rule_by_year,
        )

    return _bundle_from_metadata(metadata, compact=compact)
