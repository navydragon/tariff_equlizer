from __future__ import annotations

import numpy as np
import pandas as pd

from calculations.domain.services.route_mart_store import MartMeta

PARAMETER_COLUMN_MAP = {
    "cargo_group": "cargo_group_code",
    "cargo_code": "cargo_code",
    "origin_railroad": "origin_railroad_code",
    "destination_railroad": "destination_railroad_code",
    "wagon_kind": "wagon_kind_id",
    "shipment_type": "shipment_type_id",
    "message_type": "message_type_id",
    "shipper": "shipper_id",
    "shipper_holding": "shipper_holding",
    "distance_belt": "distance_belt",
}

_DIM_PARAMETERS = frozenset(
    {
        "cargo_group",
        "cargo_code",
        "direction",
        "wagon_kind",
        "transport_type",
        "shipment_category",
        "park_type",
        "holding",
        "origin_railroad",
        "destination_railroad",
    },
)

_CODE_FALLBACK_PARAMETERS = frozenset(
    {
        "cargo_group",
        "cargo_code",
        "origin_railroad",
        "destination_railroad",
    },
)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _label_codes(values: list, labels: list[str]) -> list[int]:
    label_to_code = {label: index for index, label in enumerate(labels)}
    codes: list[int] = []
    for value in values:
        key = str(value)
        if key in label_to_code:
            codes.append(label_to_code[key])
    return codes


def _parse_int_ids(vals: list) -> list[int]:
    ids: list[int] = []
    for value in vals:
        try:
            ids.append(int(value))
        except (TypeError, ValueError):
            continue
    return ids


def _lookup_dimension_names(parameter: str, vals: list) -> list[str]:
    ids = _parse_int_ids(vals)
    if not ids:
        return []

    if parameter == "wagon_kind":
        from core.models import WagonKind

        return list(
            WagonKind.objects.filter(pk__in=ids).values_list("name", flat=True),
        )
    if parameter == "message_type":
        from core.models import MessageType

        return list(
            MessageType.objects.filter(pk__in=ids).values_list("name", flat=True),
        )
    if parameter == "shipment_type":
        from core.models import ShipmentType

        return list(
            ShipmentType.objects.filter(pk__in=ids).values_list("name", flat=True),
        )

    return []


def _lookup_railroad_names(codes: list) -> list[str]:
    from core.models import RailRoad

    return list(
        RailRoad.objects.filter(
            code__in=[str(value) for value in codes],
        ).values_list("name", flat=True),
    )


def _resolve_dim_compare_codes(
    parameter: str,
    vals: list,
    labels: list[str],
) -> list[int]:
    compare_codes = _label_codes(vals, labels)
    if compare_codes:
        return compare_codes

    if parameter == "cargo_group":
        from core.models import CargoGroup

        names = list(
            CargoGroup.objects.filter(
                code__in=[str(value) for value in vals],
            ).values_list("name", flat=True),
        )
        return _label_codes(names, labels)

    if parameter in {"origin_railroad", "destination_railroad"}:
        names = _lookup_railroad_names(vals)
        return _label_codes(names, labels)

    names = _lookup_dimension_names(parameter, vals)
    if names:
        return _label_codes(names, labels)

    return []


def build_rule_mask_numpy(
    df: pd.DataFrame,
    conditions: list[dict],
    *,
    mart_meta: MartMeta | None = None,
) -> np.ndarray:
    if df.empty:
        return np.zeros(0, dtype=bool)

    mask = np.ones(len(df), dtype=bool)

    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        if parameter == "distance_belt" and operator in ("include", "exclude"):
            if "distance_belt" not in df.columns:
                continue
            belt_vals = [
                str(v) for v in _as_list(values) if v is not None and str(v) != ""
            ]
            if not belt_vals:
                continue
            series = df["distance_belt"].fillna("").astype(str).to_numpy()
            if operator == "include":
                mask &= np.isin(series, belt_vals)
            elif operator == "exclude":
                mask &= ~np.isin(series, belt_vals)
            continue

        if parameter == "distance_belt" and operator in ("lt", "gt"):
            if "distance_belt_midpoint_km" not in df.columns:
                continue
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            series = pd.to_numeric(
                df["distance_belt_midpoint_km"], errors="coerce"
            ).to_numpy(dtype=np.float64)
            if operator == "lt":
                mask &= np.nan_to_num(series, nan=np.inf) < num
            elif operator == "gt":
                mask &= np.nan_to_num(series, nan=-1.0) > num
            continue

        column = PARAMETER_COLUMN_MAP.get(parameter)
        if not column or not operator:
            continue

        vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
        if not vals:
            continue

        dim_parameter = "holding" if parameter == "shipper_holding" else parameter
        dim_column = (
            f"dim_{dim_parameter}" if dim_parameter in _DIM_PARAMETERS else None
        )

        if dim_column and dim_column in df.columns and mart_meta is not None:
            labels = mart_meta.dimension_labels.get(dim_parameter, [])
            compare_codes = _resolve_dim_compare_codes(dim_parameter, vals, labels)
            if not compare_codes:
                if parameter in _CODE_FALLBACK_PARAMETERS and column in df.columns:
                    compare_vals = [str(v) for v in vals]
                    series = df[column].astype(str).to_numpy()
                    if operator == "include":
                        mask &= np.isin(series, compare_vals)
                    elif operator == "exclude":
                        mask &= ~np.isin(series, compare_vals)
                else:
                    mask &= False
                continue
            series = df[dim_column].to_numpy(dtype=np.int32, copy=False)
            if operator == "include":
                mask &= np.isin(series, compare_codes)
            elif operator == "exclude":
                mask &= ~np.isin(series, compare_codes)
            continue

        if column not in df.columns:
            continue

        series = df[column]
        if parameter in {"wagon_kind", "shipment_type", "message_type", "shipper"}:
            compare_vals: list = []
            for val in vals:
                try:
                    compare_vals.append(int(val))
                except (TypeError, ValueError):
                    compare_vals.append(val)
            arr = series.to_numpy()
            if operator == "include":
                mask &= np.isin(arr, compare_vals)
            elif operator == "exclude":
                mask &= ~np.isin(arr, compare_vals)
            continue

        compare_vals = vals
        arr = series.astype(str).to_numpy()
        if operator == "include":
            mask &= np.isin(arr, compare_vals)
        elif operator == "exclude":
            mask &= ~np.isin(arr, compare_vals)

    return mask


def build_rule_mask(df: pd.DataFrame, conditions: list[dict]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)

    mask = pd.Series(True, index=df.index)

    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        if parameter == "distance_belt" and operator in ("include", "exclude"):
            if "distance_belt" not in df.columns:
                continue
            belt_vals = [
                str(v) for v in _as_list(values) if v is not None and str(v) != ""
            ]
            if not belt_vals:
                continue
            series = df["distance_belt"].fillna("").astype(str)
            if operator == "include":
                mask &= series.isin(belt_vals)
            elif operator == "exclude":
                mask &= ~series.isin(belt_vals)
            continue

        if parameter == "distance_belt" and operator in ("lt", "gt"):
            if "distance_belt_midpoint_km" not in df.columns:
                continue
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            series = pd.to_numeric(df["distance_belt_midpoint_km"], errors="coerce")
            if operator == "lt":
                mask &= series < num
            elif operator == "gt":
                mask &= series > num
            continue

        column = PARAMETER_COLUMN_MAP.get(parameter)
        if not column or not operator or column not in df.columns:
            continue

        vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
        if not vals:
            continue

        series = df[column]
        if parameter in {"wagon_kind", "shipment_type", "message_type", "shipper"}:
            compare_vals = []
            for val in vals:
                try:
                    compare_vals.append(int(val))
                except (TypeError, ValueError):
                    compare_vals.append(val)
        else:
            compare_vals = vals

        if operator == "include":
            mask &= series.isin(compare_vals)
        elif operator == "exclude":
            mask &= ~series.isin(compare_vals)

    return mask.fillna(False)
