from __future__ import annotations

import json
import os
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path

import numpy as np
from django.conf import settings

from calculations.domain.services.scenario_effects_cache import CompactRouteEffects
from calculations.domain.services.scenario_effects_compact import _DIMENSION_COLUMNS
from calculations.domain.services.scenario_effects_formatting import GlobalTotals

NPZ_FILENAME = "arrays.npz"
RULE_BY_YEAR_FILENAME = "rule_by_year.npy"
METADATA_FILENAME = "metadata.json"


@dataclass
class ScenarioComputeBundle:
    compact: CompactRouteEffects
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


def _atomic_replace(tmp_path: Path, final_path: Path) -> None:
    os.replace(tmp_path, final_path)


def _save_rule_by_year(path: Path, rule_by_year: np.ndarray) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp_base = path.with_name(path.stem + ".tmp")
    np.save(tmp_base, rule_by_year.astype(np.float32, copy=False))
    _atomic_replace(Path(f"{tmp_base}.npy"), path)


def _load_rule_by_year(cache_dir: Path, data) -> np.ndarray | None:
    sidecar = cache_dir / RULE_BY_YEAR_FILENAME
    if sidecar.is_file():
        loaded = np.load(sidecar, mmap_mode="r")
        return np.asarray(loaded, dtype=np.float64)

    if data is not None and "rule_by_year" in data.files:
        return data["rule_by_year"].astype(np.float64, copy=False)
    return None


def save_scenario_compute(
    *,
    scenario_id: int,
    data_version: str,
    bundle: ScenarioComputeBundle,
) -> Path:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    cache_dir.mkdir(parents=True, exist_ok=True)

    compact = bundle.compact
    arrays = _compact_arrays_for_store(compact)

    tmp_base = cache_dir / "arrays.tmp"
    np.savez(tmp_base, **arrays)
    _atomic_replace(Path(f"{tmp_base}.npz"), cache_dir / NPZ_FILENAME)

    if compact.rule_by_year is not None:
        _save_rule_by_year(cache_dir / RULE_BY_YEAR_FILENAME, compact.rule_by_year)

    metadata = {
        "years": compact.years,
        "dimension_labels": compact.dimension_labels,
        "rule_meta": [[rule_id, name] for rule_id, name in compact.rule_meta],
        "filter_options": bundle.filter_options,
        "global_totals": _global_totals_to_json(bundle.global_totals),
        "skipped_charge": bundle.skipped_charge,
        "routes_without_volume": bundle.routes_without_volume,
    }
    meta_path = cache_dir / METADATA_FILENAME
    tmp_meta = cache_dir / (METADATA_FILENAME + ".tmp")
    tmp_meta.write_text(json.dumps(metadata, ensure_ascii=False), encoding="utf-8")
    _atomic_replace(tmp_meta, meta_path)
    return cache_dir


def try_load_scenario_compute(
    *,
    scenario_id: int,
    data_version: str,
) -> ScenarioComputeBundle | None:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    npz_path = cache_dir / NPZ_FILENAME
    meta_path = cache_dir / METADATA_FILENAME
    if not npz_path.is_file() or not meta_path.is_file():
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    with np.load(npz_path, allow_pickle=False) as data:
        rule_by_year = _load_rule_by_year(cache_dir, data)
        dimensions = {
            column: data[f"dim_{column}"].astype(np.int32, copy=False)
            for column in _DIMENSION_COLUMNS
        }
        compact = CompactRouteEffects(
            years=[int(year) for year in metadata["years"]],
            dimensions=dimensions,
            dimension_labels=metadata["dimension_labels"],
            baseline_rub=data["baseline_rub"].astype(np.float64, copy=False),
            volume_tons=data["volume_tons"].astype(np.float64, copy=False),
            base_by_year=data["base_by_year"].astype(np.float64, copy=False),
            rules_by_year=data["rules_by_year"].astype(np.float64, copy=False),
            charge_by_year=data["charge_by_year"].astype(np.float64, copy=False),
            rule_meta=[(int(item[0]), str(item[1])) for item in metadata.get("rule_meta", [])],
            rule_by_year=rule_by_year,
        )

    return ScenarioComputeBundle(
        compact=compact,
        global_totals=_global_totals_from_json(metadata["global_totals"]),
        filter_options=metadata.get("filter_options") or {},
        skipped_charge=int(metadata.get("skipped_charge", 0)),
        routes_without_volume=int(metadata.get("routes_without_volume", 0)),
    )
