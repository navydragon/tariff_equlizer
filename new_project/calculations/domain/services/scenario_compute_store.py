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
from core.domain.cargo.ordering import normalize_filter_options

BASELINE_RUB_FILENAME = "baseline_rub.npy"
ROUTE_IDS_FILENAME = "route_ids.npy"
VOLUME_TONS_FILENAME = "volume_tons.npy"
VOLUME_BY_YEAR_FILENAME = "volume_by_year.npy"
VOLUME_FALLOUT_BY_YEAR_FILENAME = "volume_fallout_by_year.npy"
MONEY_FALLOUT_BY_YEAR_FILENAME = "money_fallout_by_year.npy"
BASE_BY_YEAR_FILENAME = "base_by_year.npy"
RULES_BY_YEAR_FILENAME = "rules_by_year.npy"
CHARGE_BY_YEAR_FILENAME = "charge_by_year.npy"
RULE_BY_YEAR_FILENAME = "rule_by_year.npy"
METADATA_FILENAME = "metadata.json"


@dataclass
class ScenarioComputeBundle:
    compact: CompactRouteEffects | None
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
        BASELINE_RUB_FILENAME: compact.baseline_rub.astype(np.float32, copy=False),
        VOLUME_TONS_FILENAME: compact.volume_tons.astype(np.float32, copy=False),
        BASE_BY_YEAR_FILENAME: compact.base_by_year.astype(np.float32, copy=False),
        RULES_BY_YEAR_FILENAME: compact.rules_by_year.astype(np.float32, copy=False),
        CHARGE_BY_YEAR_FILENAME: compact.charge_by_year.astype(np.float32, copy=False),
    }
    if compact.route_ids is not None:
        arrays[ROUTE_IDS_FILENAME] = compact.route_ids.astype(np.int32, copy=False)
    if compact.volume_by_year is not None:
        arrays[VOLUME_BY_YEAR_FILENAME] = compact.volume_by_year.astype(
            np.float32,
            copy=False,
        )
    if compact.volume_fallout_by_year is not None:
        arrays[VOLUME_FALLOUT_BY_YEAR_FILENAME] = compact.volume_fallout_by_year.astype(
            np.float32,
            copy=False,
        )
    if compact.money_fallout_by_year is not None:
        arrays[MONEY_FALLOUT_BY_YEAR_FILENAME] = compact.money_fallout_by_year.astype(
            np.float32,
            copy=False,
        )
    for column in _DIMENSION_COLUMNS:
        arrays[_dimension_filename(column)] = compact.dimensions[column].astype(
            np.int32,
            copy=False,
        )
    return arrays


def _dimension_filename(column: str) -> str:
    return f"dim_{column}.npy"


def _dimension_path(cache_dir: Path, column: str) -> Path:
    return cache_dir / _dimension_filename(column)


def _compact_array_paths(cache_dir: Path) -> dict[str, Path]:
    return {
        "baseline_rub": cache_dir / BASELINE_RUB_FILENAME,
        "volume_tons": cache_dir / VOLUME_TONS_FILENAME,
        "base_by_year": cache_dir / BASE_BY_YEAR_FILENAME,
        "rules_by_year": cache_dir / RULES_BY_YEAR_FILENAME,
        "charge_by_year": cache_dir / CHARGE_BY_YEAR_FILENAME,
    }


def _compact_required_paths(cache_dir: Path) -> list[Path]:
    paths = list(_compact_array_paths(cache_dir).values())
    paths.extend(_dimension_path(cache_dir, column) for column in _DIMENSION_COLUMNS)
    return paths


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


def _save_npy_array(array: np.ndarray, out_path: Path) -> None:
    out_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_base = out_path.parent / (out_path.stem + ".tmp")
    np.save(tmp_base, array)
    _atomic_replace(Path(f"{tmp_base}.npy"), out_path)


def _load_npy_mmap(path: Path, *, dtype=None) -> np.ndarray | None:
    if not path.is_file():
        return None
    loaded = np.load(path, mmap_mode="r")
    if dtype is None:
        return np.asarray(loaded)
    return np.asarray(loaded, dtype=dtype)


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
    # На Windows в тестах/параллельных warm-потоках возможно удаление cache_dir
    # между записью tmp и replace (purge/cleanup). Поэтому делаем запись+replace
    # с повторной генерацией tmp-файла при ретраях.
    last_error: OSError | None = None
    for attempt in range(12):
        try:
            cache_dir.mkdir(parents=True, exist_ok=True)
            tmp_meta = cache_dir / (METADATA_FILENAME + f".tmp.{attempt}")
            tmp_meta.write_text(
                json.dumps(metadata, ensure_ascii=False),
                encoding="utf-8",
            )
            _atomic_replace(tmp_meta, meta_path, max_attempts=1)
            return
        except OSError as exc:
            last_error = exc
            time.sleep(0.05 * (attempt + 1))
    if last_error is not None:
        raise last_error


def _remove_compact_sidecars(
    cache_dir: Path,
    *,
    scenario_id: int | None = None,
    data_version: str | None = None,
) -> None:
    skip_compact = False
    if scenario_id is not None and data_version is not None:
        from calculations.domain.services.scenario_effects_deferred import (
            is_deferred_running,
        )

        skip_compact = is_deferred_running(scenario_id, data_version)

    if skip_compact:
        return

    for path in (
        _compact_required_paths(cache_dir)
        + [
            cache_dir / RULE_BY_YEAR_FILENAME,
            cache_dir / VOLUME_BY_YEAR_FILENAME,
            cache_dir / VOLUME_FALLOUT_BY_YEAR_FILENAME,
            cache_dir / MONEY_FALLOUT_BY_YEAR_FILENAME,
        ]
    ):
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
    for filename, array in arrays.items():
        _save_npy_array(array, cache_dir / filename)

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
    return all(path.is_file() for path in _compact_required_paths(cache_dir))


def try_load_scenario_compute(
    *,
    scenario_id: int,
    data_version: str,
) -> ScenarioComputeBundle | None:
    cache_dir = scenario_compute_dir(scenario_id=scenario_id, data_version=data_version)
    meta_path = cache_dir / METADATA_FILENAME
    if not meta_path.is_file():
        return None

    metadata = json.loads(meta_path.read_text(encoding="utf-8"))
    if metadata.get("kpi_only"):
        return ScenarioComputeBundle(
            compact=None,
            global_totals=_global_totals_from_json(metadata["global_totals"]),
            filter_options=normalize_filter_options(metadata.get("filter_options") or {}),
            skipped_charge=int(metadata.get("skipped_charge", 0)),
            routes_without_volume=int(metadata.get("routes_without_volume", 0)),
        )

    if not is_scenario_compact_on_disk(
        scenario_id=scenario_id,
        data_version=data_version,
    ):
        return None

    compact_arrays = _compact_array_paths(cache_dir)
    baseline_rub = _load_npy_mmap(compact_arrays["baseline_rub"], dtype=np.float32)
    route_ids_path = cache_dir / ROUTE_IDS_FILENAME
    route_ids = (
        _load_npy_mmap(route_ids_path, dtype=np.int32)
        if route_ids_path.is_file()
        else None
    )
    volume_tons = _load_npy_mmap(compact_arrays["volume_tons"], dtype=np.float32)
    volume_by_year_path = cache_dir / VOLUME_BY_YEAR_FILENAME
    volume_by_year = (
        _load_npy_mmap(volume_by_year_path, dtype=np.float32)
        if volume_by_year_path.is_file()
        else None
    )
    volume_fallout_path = cache_dir / VOLUME_FALLOUT_BY_YEAR_FILENAME
    volume_fallout_by_year = (
        _load_npy_mmap(volume_fallout_path, dtype=np.float32)
        if volume_fallout_path.is_file()
        else None
    )
    money_fallout_path = cache_dir / MONEY_FALLOUT_BY_YEAR_FILENAME
    money_fallout_by_year = (
        _load_npy_mmap(money_fallout_path, dtype=np.float32)
        if money_fallout_path.is_file()
        else None
    )
    base_by_year = _load_npy_mmap(compact_arrays["base_by_year"], dtype=np.float32)
    rules_by_year = _load_npy_mmap(compact_arrays["rules_by_year"], dtype=np.float32)
    charge_by_year = _load_npy_mmap(compact_arrays["charge_by_year"], dtype=np.float32)
    dimensions = {
        column: _load_npy_mmap(_dimension_path(cache_dir, column), dtype=np.int32)
        for column in _DIMENSION_COLUMNS
    }
    if (
        baseline_rub is None
        or volume_tons is None
        or base_by_year is None
        or rules_by_year is None
        or charge_by_year is None
        or any(value is None for value in dimensions.values())
    ):
        return None
    compact = CompactRouteEffects(
        years=[int(year) for year in metadata["years"]],
        dimensions={column: value for column, value in dimensions.items() if value is not None},
        dimension_labels=metadata.get("dimension_labels") or {},
        route_ids=route_ids,
        baseline_rub=baseline_rub,
        volume_tons=volume_tons,
        base_by_year=base_by_year,
        rules_by_year=rules_by_year,
        charge_by_year=charge_by_year,
        rule_meta=[(int(item[0]), str(item[1])) for item in metadata.get("rule_meta", [])],
        rule_by_year=_load_rule_by_year(cache_dir, None),
        volume_by_year=volume_by_year,
        volume_fallout_by_year=volume_fallout_by_year,
        money_fallout_by_year=money_fallout_by_year,
    )

    return ScenarioComputeBundle(
        compact=compact,
        global_totals=_global_totals_from_json(metadata["global_totals"]),
        filter_options=normalize_filter_options(metadata.get("filter_options") or {}),
        skipped_charge=int(metadata.get("skipped_charge", 0)),
        routes_without_volume=int(metadata.get("routes_without_volume", 0)),
    )
