from __future__ import annotations

import numpy as np
import pandas as pd

from calculations.domain.services.route_mart_store import MartMeta, MartSidecarView
from core.domain.cargo.formatting import format_cargo_code_3

_CARGO_CODE_3_COLUMNS = frozenset({"cargo_code_3", "cargo_code_izpod_3"})

PARAMETER_COLUMN_MAP = {
    "cargo_group": "cargo_group_code",
    "cargo_code": "cargo_code",
    "cargo_code_3": "cargo_code_3",
    "cargo_code_izpod_3": "cargo_code_izpod_3",
    "cargo_group_izpod": "cargo_group_izpod",
    "origin_railroad": "origin_railroad_code",
    "destination_railroad": "destination_railroad_code",
    "wagon_kind": "wagon_kind_id",
    "shipment_type": "shipment_type_id",
    "message_type": "message_type_id",
    "shipper": "shipper_id",
    "shipper_holding": "shipper_holding",
    "distance_belt": "distance_belt",
    "shipment_category": "shipment_category",
    "special_container_type": "special_container_type",
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


def _mask_label_key(column: str | None, value) -> str:
    if column in _CARGO_CODE_3_COLUMNS:
        return format_cargo_code_3(value)
    return str(value).strip()


def _label_codes(
    values: list,
    labels: list[str],
    *,
    column: str | None = None,
) -> list[int]:
    label_to_code: dict[str, int] = {}
    for index, label in enumerate(labels):
        key = _mask_label_key(column, label)
        if key and key not in label_to_code:
            label_to_code[key] = index
    codes: list[int] = []
    for value in values:
        key = _mask_label_key(column, value)
        if key in label_to_code:
            codes.append(label_to_code[key])
    return codes


def _mask_sidecar_codes_array(
    arr: np.ndarray,
    *,
    labels: list[str],
    compare_vals: list,
    column: str | None = None,
) -> tuple[np.ndarray, list[int]] | None:
    if not labels or not np.issubdtype(arr.dtype, np.integer):
        return None
    compare_codes = _label_codes(compare_vals, labels, column=column)
    if not compare_codes:
        return None
    return np.asarray(arr, dtype=np.int32), compare_codes


def _sidecar_has_column(sidecar: MartSidecarView | pd.DataFrame, column: str) -> bool:
    if isinstance(sidecar, MartSidecarView):
        return column in sidecar
    return column in sidecar.columns


def _sidecar_len(sidecar: MartSidecarView | pd.DataFrame) -> int:
    return len(sidecar)


def _sidecar_is_empty(sidecar: MartSidecarView | pd.DataFrame) -> bool:
    if isinstance(sidecar, MartSidecarView):
        return sidecar.empty
    return sidecar.empty


def _sidecar_column_array(
    sidecar: MartSidecarView | pd.DataFrame,
    column: str,
    *,
    dtype: np.dtype | type | None = None,
) -> np.ndarray:
    if isinstance(sidecar, MartSidecarView):
        arr = sidecar[column]
        if dtype is not None:
            return np.asarray(arr, dtype=dtype)
        return np.asarray(arr)
    series = sidecar[column]
    if dtype is not None:
        return series.to_numpy(dtype=dtype, copy=False)
    return series.to_numpy(copy=False)


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

        codes: list[int] = []
        for value in vals:
            try:
                codes.append(int(str(value).strip()))
            except (TypeError, ValueError):
                continue
        if not codes:
            return []
        names = list(
            CargoGroup.objects.filter(
                code__in=codes,
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
    sidecar: MartSidecarView | pd.DataFrame,
    conditions: list[dict],
    *,
    mart_meta: MartMeta | None = None,
) -> np.ndarray:
    if _sidecar_is_empty(sidecar):
        return np.zeros(0, dtype=bool)

    mask = np.ones(_sidecar_len(sidecar), dtype=bool)

    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        if parameter == "distance_belt" and operator in ("include", "exclude"):
            if not _sidecar_has_column(sidecar, "distance_belt"):
                continue
            belt_vals = [
                str(v) for v in _as_list(values) if v is not None and str(v) != ""
            ]
            if not belt_vals:
                continue
            arr = _sidecar_column_array(sidecar, "distance_belt")
            coded = (
                _mask_sidecar_codes_array(
                    arr,
                    labels=(mart_meta.dimension_labels.get("distance_belt", [])
                            if mart_meta is not None else []),
                    compare_vals=belt_vals,
                )
                if mart_meta is not None
                else None
            )
            if coded is not None:
                belt_arr, compare_codes = coded
                if operator == "include":
                    mask &= np.isin(belt_arr, compare_codes)
                elif operator == "exclude":
                    mask &= ~np.isin(belt_arr, compare_codes)
                continue
            if isinstance(sidecar, MartSidecarView):
                belt_arr = np.char.strip(arr.astype(str))
            else:
                belt_arr = sidecar["distance_belt"].fillna("").astype(str).to_numpy()
            if operator == "include":
                mask &= np.isin(belt_arr, belt_vals)
            elif operator == "exclude":
                mask &= ~np.isin(belt_arr, belt_vals)
            continue

        if parameter == "distance_belt" and operator in ("lt", "gt"):
            if not _sidecar_has_column(sidecar, "distance_belt_midpoint_km"):
                continue
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            series_arr = _sidecar_column_array(
                sidecar,
                "distance_belt_midpoint_km",
                dtype=np.float64,
            )
            if operator == "lt":
                mask &= np.nan_to_num(series_arr, nan=np.inf) < num
            elif operator == "gt":
                mask &= np.nan_to_num(series_arr, nan=-1.0) > num
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

        if dim_column and _sidecar_has_column(sidecar, dim_column) and mart_meta is not None:
            labels = mart_meta.dimension_labels.get(dim_parameter, [])
            compare_codes = _resolve_dim_compare_codes(dim_parameter, vals, labels)
            if not compare_codes:
                if parameter in _CODE_FALLBACK_PARAMETERS and _sidecar_has_column(
                    sidecar,
                    column,
                ):
                    compare_vals = [str(v) for v in vals]
                    series = _sidecar_column_array(sidecar, column, dtype=str)
                    if operator == "include":
                        mask &= np.isin(series, compare_vals)
                    elif operator == "exclude":
                        mask &= ~np.isin(series, compare_vals)
                else:
                    mask &= False
                continue
            series = _sidecar_column_array(sidecar, dim_column, dtype=np.int32)
            if operator == "include":
                mask &= np.isin(series, compare_codes)
            elif operator == "exclude":
                mask &= ~np.isin(series, compare_codes)
            continue

        if not _sidecar_has_column(sidecar, column):
            continue

        if parameter in {"wagon_kind", "shipment_type", "message_type", "shipper"}:
            compare_vals: list = []
            for val in vals:
                try:
                    compare_vals.append(int(val))
                except (TypeError, ValueError):
                    compare_vals.append(val)
            arr = _sidecar_column_array(sidecar, column)
            if operator == "include":
                mask &= np.isin(arr, compare_vals)
            elif operator == "exclude":
                mask &= ~np.isin(arr, compare_vals)
            continue

        compare_vals = vals
        arr = _sidecar_column_array(sidecar, column)
        if column in _CARGO_CODE_3_COLUMNS:
            compare_vals = [
                formatted
                for value in compare_vals
                if (formatted := format_cargo_code_3(value))
            ]

        coded = (
            _mask_sidecar_codes_array(
                arr,
                labels=(mart_meta.dimension_labels.get(column, [])
                        if mart_meta is not None else []),
                compare_vals=compare_vals,
                column=column,
            )
            if mart_meta is not None
            else None
        )
        if coded is not None:
            coded_arr, compare_codes = coded
            if operator == "include":
                mask &= np.isin(coded_arr, compare_codes)
            elif operator == "exclude":
                mask &= ~np.isin(coded_arr, compare_codes)
            continue

        str_arr = arr.astype(str)
        if operator == "include":
            mask &= np.isin(str_arr, compare_vals)
        elif operator == "exclude":
            mask &= ~np.isin(str_arr, compare_vals)

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
