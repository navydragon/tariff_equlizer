from __future__ import annotations

from core.models import Route


FIELD_MAP = {
    "cargo_group": "cargo__cargo_group__code",
    "cargo_code": "cargo__code",
    "origin_railroad": "origin_station__railroad__code",
    "destination_railroad": "destination_station__railroad__code",
    "wagon_kind": "wagon_kind__id",
    "shipment_type": "shipment_type__id",
    "message_type": "message_type__id",
    "shipper": "shipper_id",
    "shipper_holding": "shipper__holding",
    "distance_loaded_km": "distance_loaded_km",
}


def _as_list(value):
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def apply_tariff_conditions(qs, conditions: list[dict]):
    filtered = qs
    for condition in conditions or []:
        parameter = (condition.get("parameter") or "").strip()
        operator = (condition.get("operator") or "").strip()
        values = condition.get("values")

        field = FIELD_MAP.get(parameter)
        if not field or not operator:
            continue

        if parameter == "distance_loaded_km":
            try:
                num = int(values)
            except (TypeError, ValueError):
                continue
            if operator == "lt":
                filtered = filtered.filter(**{f"{field}__lt": num})
            elif operator == "gt":
                filtered = filtered.filter(**{f"{field}__gt": num})
            continue

        vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
        if not vals:
            continue

        if operator == "include":
            filtered = filtered.filter(**{f"{field}__in": vals})
        elif operator == "exclude":
            filtered = filtered.exclude(**{f"{field}__in": vals})

    return filtered


def route_matches_tariff_conditions(route: Route, conditions: list[dict]) -> bool:
    if not conditions:
        return True
    qs = Route.objects.filter(pk=route.pk)
    return apply_tariff_conditions(qs, conditions).exists()
