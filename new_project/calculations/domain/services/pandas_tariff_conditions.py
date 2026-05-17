from __future__ import annotations

import pandas as pd

PARAMETER_COLUMN_MAP = {
    "cargo_group": "cargo_group_code",
    "cargo_code": "cargo_code",
    "origin_railroad": "origin_railroad_code",
    "destination_railroad": "destination_railroad_code",
    "wagon_kind": "wagon_kind_id",
    "shipment_type": "shipment_type_id",
    "message_type": "message_type_id",
    "shipper_holding": "shipper_holding",
    "distance_loaded_km": "distance_loaded_km",
}


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def build_rule_mask(df: pd.DataFrame, conditions: list[dict]) -> pd.Series:
    if df.empty:
        return pd.Series(dtype=bool)

    mask = pd.Series(True, index=df.index)

    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        column = PARAMETER_COLUMN_MAP.get(parameter)
        if not column or not operator or column not in df.columns:
            continue

        if parameter == "distance_loaded_km":
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            series = pd.to_numeric(df[column], errors="coerce")
            if operator == "lt":
                mask &= series < num
            elif operator == "gt":
                mask &= series > num
            continue

        vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
        if not vals:
            continue

        series = df[column]
        if parameter in {"wagon_kind", "shipment_type", "message_type"}:
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
