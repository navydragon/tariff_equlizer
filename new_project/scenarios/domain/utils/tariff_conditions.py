from __future__ import annotations

from django.db.models import F, Value
from django.db.models.functions import Coalesce, NullIf, Trim

from core.domain.cargo.formatting import format_cargo_code_3
from core.models import Route

_CARGO_CODE_3_PARAMETERS = frozenset({"cargo_code_3", "cargo_code_izpod_3"})
_BOOL_PARAMETERS = frozenset({"is_consumer_goods", "is_food_goods"})


FIELD_MAP = {
    "cargo_group": "cargo__cargo_group__code",
    "cargo_code": "cargo__code",
    "cargo_code_3": "cargo_code_3",
    "cargo_code_izpod_3": "cargo_code_izpod_3",
    "cargo_group_izpod": "cargo_group_izpod",
    "origin_railroad": "origin_station__railroad__code",
    "destination_railroad": "destination_station__railroad__code",
    "wagon_kind": "wagon_kind__id",
    "shipment_type": "shipment_type__id",
    "message_type": "message_type__id",
    "shipper": "shipper_id",
    "shipper_holding": "shipper__holding",
    "distance_belt": "distance_belt",
    "shipment_category": "shipment_category",
    "special_container_type": "special_container_type",
    "is_consumer_goods": "cargo__is_consumer_goods",
    "is_food_goods": "cargo__is_food_goods",
}

_NORMALIZED_STRING_PARAMETERS = frozenset({"shipment_category"})


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def _parse_bool_values(values) -> list[bool]:
    parsed: list[bool] = []
    for value in _as_list(values):
        token = str(value).strip().lower()
        if token == "yes":
            parsed.append(True)
        elif token == "no":
            parsed.append(False)
    return parsed


def _annotate_normalized_string_field(qs, parameter: str):
    if parameter not in _NORMALIZED_STRING_PARAMETERS:
        return qs, parameter
    annotation_name = f"_{parameter}_norm"
    annotated = qs.annotate(
        **{
            annotation_name: Coalesce(
                NullIf(Trim(F(parameter)), Value("")),
                Value("—"),
            ),
        },
    )
    return annotated, annotation_name


def apply_tariff_conditions(qs, conditions: list[dict]):
    filtered = qs
    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        if parameter == "distance_belt" and operator in ("lt", "gt"):
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            if operator == "lt":
                filtered = filtered.filter(distance_belt_midpoint_km__lt=num)
            elif operator == "gt":
                filtered = filtered.filter(distance_belt_midpoint_km__gt=num)
            continue

        field = FIELD_MAP.get(parameter)
        if not field or not operator:
            continue

        vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
        if not vals:
            continue

        if parameter in _CARGO_CODE_3_PARAMETERS:
            vals = [
                formatted
                for value in vals
                if (formatted := format_cargo_code_3(value))
            ]
            if not vals:
                continue

        if parameter in _BOOL_PARAMETERS:
            bool_vals = _parse_bool_values(vals)
            if not bool_vals:
                continue
            if operator == "include":
                filtered = filtered.filter(**{f"{field}__in": bool_vals})
            elif operator == "exclude":
                filtered = filtered.exclude(**{f"{field}__in": bool_vals})
            continue

        compare_field = field
        if parameter in _NORMALIZED_STRING_PARAMETERS:
            filtered, compare_field = _annotate_normalized_string_field(
                filtered,
                parameter,
            )

        if operator == "include":
            filtered = filtered.filter(**{f"{compare_field}__in": vals})
        elif operator == "exclude":
            filtered = filtered.exclude(**{f"{compare_field}__in": vals})

    return filtered


def route_matches_tariff_conditions(
    route: Route,
    conditions: list[dict],
) -> bool:
    if not conditions:
        return True
    qs = Route.objects.filter(pk=route.pk)
    return apply_tariff_conditions(qs, conditions).exists()
