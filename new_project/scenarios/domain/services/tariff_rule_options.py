from __future__ import annotations

from calculations.domain.services.route_mart_store import distinct_mask_sidecar_labels
from core.models import CargoGroup, Route


def _distinct_route_values(route_set_id: int, field: str) -> list[str]:
    return list(
        Route.objects.filter(route_set_id=route_set_id)
        .exclude(**{f"{field}": ""})
        .values_list(field, flat=True)
        .distinct()
        .order_by(field)
    )


def mask_sidecar_option_items(
    *,
    route_set_id: int,
    column: str,
) -> list[dict[str, str]]:
    values = distinct_mask_sidecar_labels(route_set_id=route_set_id, column=column)
    if values is None:
        values = _distinct_route_values(route_set_id, column)
    return [{"value": value, "text": value} for value in values]


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
