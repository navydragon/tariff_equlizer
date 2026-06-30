from __future__ import annotations

from core.models import Cargo, CargoGroup, MessageType, Route, ShipmentType, WagonKind
from core.domain.cargo.formatting import (
    format_cargo_code_3,
    format_etsng_code,
    parse_etsng_code,
)


def _as_list(value) -> list:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


def resolve_condition_value_labels(*, parameter: str, values) -> list[str]:
    vals = [v for v in _as_list(values) if v is not None and str(v) != ""]
    if not vals:
        return []

    if parameter == "cargo_group":
        codes = [str(value) for value in vals]
        names = {
            str(item.code): item.name
            for item in CargoGroup.objects.filter(code__in=codes)
        }
        return [names.get(code, code) for code in codes]

    if parameter == "cargo_code":
        codes = []
        for value in vals:
            code = parse_etsng_code(value)
            if code is not None:
                codes.append(code)
        names = {
            item.code: item.name
            for item in Cargo.objects.filter(code__in=codes)
        }
        labels = []
        for value in vals:
            code = parse_etsng_code(value)
            if code is None:
                labels.append(str(value))
                continue
            name = names.get(code)
            display_code = format_etsng_code(code)
            labels.append(
                f"{display_code} — {name}" if name else display_code,
            )
        return labels

    if parameter in {"wagon_kind", "shipment_type", "message_type"}:
        model = {
            "wagon_kind": WagonKind,
            "shipment_type": ShipmentType,
            "message_type": MessageType,
        }[parameter]
        ids = []
        for value in vals:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        names = {
            str(item.id): item.name
            for item in model.objects.filter(id__in=ids)
        }
        return [names.get(str(value), str(value)) for value in vals]

    if parameter in {"cargo_code_3", "cargo_code_izpod_3"}:
        return [format_cargo_code_3(value) for value in vals]

    if parameter in {"origin_railroad", "destination_railroad", "shipper_holding", "distance_belt"}:
        return [str(value) for value in vals]

    if parameter == "shipper":
        ids = []
        for value in vals:
            try:
                ids.append(int(value))
            except (TypeError, ValueError):
                continue
        rows = (
            Route.objects.filter(shipper_id__in=ids)
            .exclude(shipper__isnull=True)
            .values("shipper_id", "shipper__name", "shipper__holding")
            .distinct()
        )
        labels = {}
        for row in rows:
            shipper_id = str(row["shipper_id"])
            holding = row.get("shipper__holding") or ""
            name = row.get("shipper__name") or shipper_id
            labels[shipper_id] = f"{name} ({holding})" if holding else name
        return [labels.get(str(value), str(value)) for value in vals]

    return [str(value) for value in vals]


def enrich_rule_dict_for_api(rule_dict: dict, *, route_set_id: int) -> dict:
    del route_set_id  # reserved for route-scoped labels if needed later
    conditions = rule_dict.get("conditions") or []
    for condition in conditions:
        labels = resolve_condition_value_labels(
            parameter=condition.get("parameter") or "",
            values=condition.get("values"),
        )
        condition["values_display"] = labels
    return rule_dict
