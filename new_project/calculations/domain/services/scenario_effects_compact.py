from __future__ import annotations

from collections import defaultdict
from decimal import Decimal
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from calculations.domain.services.route_mart_store import MartMeta

from calculations.domain.services.scenario_effects_cache import CompactRouteEffects

_DIMENSION_COLUMNS = (
    "cargo_group",
    "cargo_code",
    "direction",
    "wagon_kind",
    "transport_type",
    "shipment_category",
    "park_type",
    "holding",
)

_FLOAT_DTYPE = np.float32
_COMPUTE_DTYPE = np.float64


def extract_volume_array(df: pd.DataFrame) -> np.ndarray:
    if "transport_volume_tons" not in df.columns:
        return np.zeros(len(df), dtype=_FLOAT_DTYPE)
    series = df["transport_volume_tons"]
    if pd.api.types.is_numeric_dtype(series):
        return np.nan_to_num(
            series.to_numpy(dtype=_FLOAT_DTYPE, copy=False),
            nan=0.0,
        )
    return (
        pd.to_numeric(series, errors="coerce")
        .fillna(0)
        .to_numpy(dtype=_FLOAT_DTYPE)
    )


def _as_float32(array: np.ndarray) -> np.ndarray:
    if array.dtype == _FLOAT_DTYPE:
        return array
    return array.astype(_FLOAT_DTYPE, copy=False)


def prepare_compact_inputs(
    df: pd.DataFrame,
    mart_meta: MartMeta | None,
) -> tuple[dict[str, np.ndarray], dict[str, list[str]], np.ndarray]:
    dimensions: dict[str, np.ndarray] = {}
    dimension_labels: dict[str, list[str]] = {}

    if mart_meta is not None and mart_meta.dimension_labels:
        dimensions = {
            column: df[f"dim_{column}"].to_numpy(dtype=np.int32, copy=False)
            for column in _DIMENSION_COLUMNS
            if f"dim_{column}" in df.columns
        }
        dimension_labels = mart_meta.dimension_labels
    else:
        for column in _DIMENSION_COLUMNS:
            dim_column = f"dim_{column}"
            if dim_column in df.columns:
                dimensions[column] = df[dim_column].to_numpy(dtype=np.int32, copy=False)
                if mart_meta and mart_meta.dimension_labels.get(column):
                    dimension_labels[column] = mart_meta.dimension_labels[column]
                else:
                    dimension_labels[column] = df[column].astype(str).unique().tolist()
            elif column in df.columns:
                series = df[column].astype(str)
                codes, uniques = pd.factorize(series, sort=False)
                dimensions[column] = codes.astype(np.int32, copy=False)
                dimension_labels[column] = uniques.tolist()

    volume = extract_volume_array(df)
    return dimensions, dimension_labels, volume


def build_compact_from_arrays(
    df: pd.DataFrame | None = None,
    *,
    years: list[int],
    initial: np.ndarray,
    base_by_year: np.ndarray,
    rules_by_year_arr: np.ndarray,
    charge_by_year: np.ndarray,
    rule_meta: list[tuple[int, str]] | None = None,
    rule_by_year: np.ndarray | None = None,
    dimensions: dict[str, np.ndarray] | None = None,
    dimension_labels: dict[str, list[str]] | None = None,
    volume: np.ndarray | None = None,
) -> CompactRouteEffects:
    resolved_dimensions: dict[str, np.ndarray] = {}
    resolved_labels: dict[str, list[str]] = {}

    if dimensions is not None and dimension_labels is not None:
        resolved_dimensions = dimensions
        resolved_labels = dimension_labels
    elif df is not None:
        for column in _DIMENSION_COLUMNS:
            dim_column = f"dim_{column}"
            if dim_column in df.columns:
                resolved_dimensions[column] = df[dim_column].astype(np.int32, copy=False)
                if dimension_labels and column in dimension_labels:
                    resolved_labels[column] = dimension_labels[column]
                else:
                    resolved_labels[column] = df[column].astype(str).unique().tolist()
                continue
            series = df[column].astype(str)
            codes, uniques = pd.factorize(series, sort=False)
            resolved_dimensions[column] = codes.astype(np.int32, copy=False)
            resolved_labels[column] = uniques.tolist()
    else:
        raise ValueError("dimensions and dimension_labels or df are required")

    if volume is None:
        if df is None:
            raise ValueError("volume or df is required")
        volume = extract_volume_array(df)

    return CompactRouteEffects(
        years=years,
        dimensions=resolved_dimensions,
        dimension_labels=resolved_labels,
        baseline_rub=_as_float32(initial),
        volume_tons=_as_float32(volume),
        base_by_year=_as_float32(base_by_year),
        rules_by_year=_as_float32(rules_by_year_arr),
        charge_by_year=_as_float32(charge_by_year),
        rule_meta=list(rule_meta or []),
        rule_by_year=(
            _as_float32(rule_by_year)
            if rule_by_year is not None
            else None
        ),
    )


def _label_for_code(compact: CompactRouteEffects, dimension: str, code: int) -> str:
    labels = compact.dimension_labels.get(dimension, [])
    if 0 <= code < len(labels):
        return labels[code]
    return "—"


def _filtered_frame(compact: CompactRouteEffects, mask: np.ndarray) -> pd.DataFrame:
    data: dict[str, np.ndarray] = {
        column: compact.dimensions[column][mask]
        for column in _DIMENSION_COLUMNS
    }
    return pd.DataFrame(data)


def _build_mask(
    compact: CompactRouteEffects,
    *,
    cargo_filter: set[str] | None,
    holding_filter: set[str] | None,
) -> np.ndarray:
    mask = np.ones(len(compact.baseline_rub), dtype=bool)
    if cargo_filter is not None:
        allowed = {
            idx
            for idx, label in enumerate(compact.dimension_labels["cargo_group"])
            if label in cargo_filter
        }
        mask &= np.isin(compact.dimensions["cargo_group"], list(allowed))
    if holding_filter is not None:
        allowed = {
            idx
            for idx, label in enumerate(compact.dimension_labels["holding"])
            if label in holding_filter
        }
        mask &= np.isin(compact.dimensions["holding"], list(allowed))
    return mask


def aggregate_compact_buckets(
    compact: CompactRouteEffects,
    *,
    year: int,
    prev_year: int,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
) -> dict[tuple[str, ...], tuple[Decimal, Decimal, Decimal]]:
    year_index = compact.years.index(year)
    prev_year_index = compact.years.index(prev_year)
    mask = _build_mask(
        compact,
        cargo_filter=set(cargo_groups) if cargo_groups else None,
        holding_filter=set(holdings) if holdings else None,
    )

    frame = _filtered_frame(compact, mask)
    if frame.empty:
        return {}

    frame["base"] = compact.base_by_year[mask, year_index]
    frame["rules"] = compact.rules_by_year[mask, year_index]
    frame["prev_charge"] = compact.charge_by_year[mask, prev_year_index]

    outer_col = group_by if group_by in frame.columns else "cargo_group"
    buckets: dict[tuple[str, ...], tuple[Decimal, Decimal, Decimal]] = {}

    if group_by_inner == "none":
        grouped = frame.groupby(outer_col, sort=False)[["base", "rules", "prev_charge"]].sum()
        for code, row in grouped.iterrows():
            label = _label_for_code(compact, outer_col, int(code))
            buckets[(label,)] = (
                Decimal(str(row["base"])),
                Decimal(str(row["rules"])),
                Decimal(str(row["prev_charge"])),
            )
        return buckets

    inner_col = group_by_inner
    outer_grouped = frame.groupby(outer_col, sort=False)[["base", "rules", "prev_charge"]].sum()
    for outer_code, row in outer_grouped.iterrows():
        outer_label = _label_for_code(compact, outer_col, int(outer_code))
        buckets[(outer_label, "ИТОГО")] = (
            Decimal(str(row["base"])),
            Decimal(str(row["rules"])),
            Decimal(str(row["prev_charge"])),
        )

    detail_grouped = frame.groupby([outer_col, inner_col], sort=False)[
        ["base", "rules", "prev_charge"]
    ].sum()
    for (outer_code, inner_code), row in detail_grouped.iterrows():
        outer_label = _label_for_code(compact, outer_col, int(outer_code))
        inner_label = _label_for_code(compact, inner_col, int(inner_code))
        buckets[(outer_label, inner_label)] = (
            Decimal(str(row["base"])),
            Decimal(str(row["rules"])),
            Decimal(str(row["prev_charge"])),
        )

    return buckets


def aggregate_compact_value(
    compact: CompactRouteEffects,
    *,
    values: np.ndarray,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
) -> dict[tuple[str, ...], Decimal]:
    mask = _build_mask(
        compact,
        cargo_filter=set(cargo_groups) if cargo_groups else None,
        holding_filter=set(holdings) if holdings else None,
    )
    frame = _filtered_frame(compact, mask)
    if frame.empty:
        return {}

    frame["value"] = values[mask]
    outer_col = group_by if group_by in frame.columns else "cargo_group"
    buckets: dict[tuple[str, ...], Decimal] = defaultdict(Decimal)

    if group_by_inner == "none":
        grouped = frame.groupby(outer_col, sort=False)["value"].sum()
        for code, value in grouped.items():
            label = _label_for_code(compact, outer_col, int(code))
            buckets[(label,)] += Decimal(str(value))
        return buckets

    inner_col = group_by_inner
    outer_grouped = frame.groupby(outer_col, sort=False)["value"].sum()
    for outer_code, value in outer_grouped.items():
        outer_label = _label_for_code(compact, outer_col, int(outer_code))
        buckets[(outer_label, "ИТОГО")] += Decimal(str(value))

    detail_grouped = frame.groupby([outer_col, inner_col], sort=False)["value"].sum()
    for (outer_code, inner_code), value in detail_grouped.items():
        outer_label = _label_for_code(compact, outer_col, int(outer_code))
        inner_label = _label_for_code(compact, inner_col, int(inner_code))
        buckets[(outer_label, inner_label)] += Decimal(str(value))

    return buckets


def aggregate_compact_year_values(
    compact: CompactRouteEffects,
    *,
    group_by: str,
    group_by_inner: str,
    cargo_groups: list[str],
    holdings: list[str],
    values_by_year: np.ndarray,
) -> dict[tuple[str, ...], dict[int, Decimal]]:
    year_values: dict[tuple[str, ...], dict[int, Decimal]] = {}
    for year_index, year in enumerate(compact.years):
        buckets = aggregate_compact_value(
            compact,
            values=values_by_year[:, year_index],
            group_by=group_by,
            group_by_inner=group_by_inner,
            cargo_groups=cargo_groups,
            holdings=holdings,
        )
        for key, value in buckets.items():
            year_values.setdefault(key, {})[year] = value
    return year_values
