from __future__ import annotations

from calculations.domain.services.route_mart_store import distinct_mask_sidecar_labels
from core.domain.cargo.formatting import format_cargo_code_3
from core.models import CargoGroup, Route

_CARGO_CODE_3_COLUMNS = frozenset({"cargo_code_3", "cargo_code_izpod_3"})


def _distinct_route_values(route_set_id: int, field: str) -> list[str]:
    return list(
        Route.objects.filter(route_set_id=route_set_id)
        .exclude(**{f"{field}": ""})
        .values_list(field, flat=True)
        .distinct()
        .order_by(field)
    )


def _format_mask_option_value(column: str, value: str) -> str:
    if column in _CARGO_CODE_3_COLUMNS:
        return format_cargo_code_3(value)
    return value


def mask_sidecar_option_items(
    *,
    route_set_id: int,
    column: str,
) -> list[dict[str, str]]:
    values = distinct_mask_sidecar_labels(route_set_id=route_set_id, column=column)
    if values is None:
        values = _distinct_route_values(route_set_id, column)
    formatted = [_format_mask_option_value(column, value) for value in values]
    unique_values: list[str] = []
    seen: set[str] = set()
    for value in formatted:
        if not value or value in seen:
            continue
        seen.add(value)
        unique_values.append(value)
    return [{"value": value, "text": value} for value in unique_values]


def cargo_group_izpod_option_items(*, route_set_id: int) -> list[dict[str, str]]:
    values = distinct_mask_sidecar_labels(
        route_set_id=route_set_id,
        column="cargo_group_izpod",
    )
    if values is None:
        values = _distinct_route_values(route_set_id, "cargo_group_izpod")

    distinct_names = {str(value).strip() for value in values if str(value).strip()}
    if not distinct_names:
        return []

    matched_groups = list(
        CargoGroup.objects.filter(name__in=distinct_names).order_by("position", "code")
    )
    matched_names = {group.name for group in matched_groups}
    items = [{"value": group.name, "text": group.name} for group in matched_groups]
    for name in sorted(distinct_names - matched_names):
        items.append({"value": name, "text": name})
    return items
