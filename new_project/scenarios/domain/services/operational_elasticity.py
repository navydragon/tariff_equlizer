from __future__ import annotations

from collections import defaultdict
from collections.abc import Callable
from dataclasses import dataclass
from decimal import Decimal

from django.db.models import CharField, Q, Value
from django.db.models.functions import Coalesce, NullIf, Trim

from core.models import Route, RouteSet
from scenarios.domain.repositories.operational_elasticity import (
    ModelRouteEconomicsRow,
    OperationalElasticityRepository,
)

ElasticityProgressWriter = Callable[[str], None]


@dataclass
class ElasticitySourceAssignmentStats:
    direct_model: int = 0
    holding_aggregate: int = 0
    cargo_group_aggregate: int = 0
    skipped: int = 0


def _holding_key(row: ModelRouteEconomicsRow) -> str:
    return row.holding or "Прочие"


def _direction_key(row: ModelRouteEconomicsRow) -> str:
    direction = (row.direction or "").strip()
    return direction or "—"


def _holding_group_key(row: ModelRouteEconomicsRow) -> tuple:
    return (
        _holding_key(row),
        _direction_key(row),
        row.message_type_id,
        row.cargo_group_id,
    )


def _cargo_group_key(row: ModelRouteEconomicsRow) -> tuple:
    return (
        row.cargo_group_id,
        _direction_key(row),
        row.message_type_id,
    )


def build_model_route_group_indexes(
    model_rows: list[ModelRouteEconomicsRow],
) -> tuple[
    dict[tuple, list[ModelRouteEconomicsRow]],
    dict[tuple, list[ModelRouteEconomicsRow]],
]:
    holding_groups: dict[tuple, list[ModelRouteEconomicsRow]] = defaultdict(list)
    cargo_groups: dict[tuple, list[ModelRouteEconomicsRow]] = defaultdict(list)
    for row in model_rows:
        volume = row.transport_volume_tons
        if volume is None or volume <= 0:
            continue
        holding_groups[_holding_group_key(row)].append(row)
        cargo_groups[_cargo_group_key(row)].append(row)
    return holding_groups, cargo_groups


def _annotate_operational_keys(queryset):
    return queryset.annotate(
        op_holding=Coalesce(
            NullIf(Trim("shipper__holding"), Value("")),
            Value("Прочие"),
            output_field=CharField(),
        ),
        op_direction=Coalesce(
            NullIf(Trim("origin_station__railroad__direction"), Value("")),
            Value("—"),
            output_field=CharField(),
        ),
    )


def _holding_group_filter(holding_keys: list[tuple]) -> Q:
    clause = Q()
    for holding, direction, message_type_id, cargo_group_id in holding_keys:
        group_q = Q(
            op_holding=holding,
            op_direction=direction,
            message_type_id=message_type_id,
        )
        if cargo_group_id is None:
            group_q &= Q(cargo__cargo_group_id__isnull=True)
        else:
            group_q &= Q(cargo__cargo_group_id=cargo_group_id)
        clause |= group_q
    return clause


def _cargo_group_filter(cargo_keys: list[tuple]) -> Q:
    clause = Q()
    for cargo_group_id, direction, message_type_id in cargo_keys:
        group_q = Q(
            op_direction=direction,
            message_type_id=message_type_id,
        )
        if cargo_group_id is None:
            group_q &= Q(cargo__cargo_group_id__isnull=True)
        else:
            group_q &= Q(cargo__cargo_group_id=cargo_group_id)
        clause |= group_q
    return clause


def _format_route_count(value: int) -> str:
    return f"{value:,}".replace(",", " ")


def _report(progress: ElasticityProgressWriter | None, message: str) -> None:
    if progress is not None:
        progress(message)


def assign_operational_elasticity_sources(
    route_set: RouteSet,
    *,
    repository: OperationalElasticityRepository | None = None,
    progress: ElasticityProgressWriter | None = None,
) -> ElasticitySourceAssignmentStats:
    repo = repository or OperationalElasticityRepository()
    stats = ElasticitySourceAssignmentStats()

    _report(progress, "Разметка эластичности: сброс флагов…")
    reset_count = repo.reset_operational_elasticity_flags(route_set)
    _report(
        progress,
        f"Разметка эластичности: сброс флагов — "
        f"{_format_route_count(reset_count)} operational-маршрутов",
    )

    model_rows = repo.list_model_routes(route_set.id)
    holding_groups, cargo_groups = build_model_route_group_indexes(model_rows)
    holding_keys = list(holding_groups.keys())
    cargo_keys = list(cargo_groups.keys())
    _report(
        progress,
        "Разметка эластичности: индексы model-маршрутов — "
        f"{len(model_rows)} шт., групп holding {len(holding_keys)}, "
        f"групп cargo {len(cargo_keys)}",
    )

    operational = Route.objects.operational().filter(route_set=route_set)

    _report(progress, "Разметка эластичности: direct_model…")
    stats.direct_model = operational.filter(
        model_route_id__isnull=False,
    ).update(
        skip_elasticity=False,
        elasticity_source=Route.ElasticitySource.DIRECT_MODEL,
    )
    _report(
        progress,
        f"Разметка эластичности: direct_model — "
        f"{_format_route_count(stats.direct_model)}",
    )

    if holding_keys:
        _report(
            progress,
            f"Разметка эластичности: holding_aggregate "
            f"({len(holding_keys)} групп)…",
        )
        holding_clause = _holding_group_filter(holding_keys)
        stats.holding_aggregate = _annotate_operational_keys(
            operational.filter(
                model_route_id__isnull=True,
                skip_elasticity=True,
            ),
        ).filter(holding_clause).update(
            skip_elasticity=False,
            elasticity_source=Route.ElasticitySource.HOLDING_AGGREGATE,
        )
    else:
        stats.holding_aggregate = 0
    _report(
        progress,
        f"Разметка эластичности: holding_aggregate — "
        f"{_format_route_count(stats.holding_aggregate)}",
    )

    if cargo_keys:
        _report(
            progress,
            f"Разметка эластичности: cargo_group_aggregate "
            f"({len(cargo_keys)} групп)…",
        )
        cargo_clause = _cargo_group_filter(cargo_keys)
        stats.cargo_group_aggregate = _annotate_operational_keys(
            operational.filter(
                model_route_id__isnull=True,
                skip_elasticity=True,
            ),
        ).filter(cargo_clause).update(
            skip_elasticity=False,
            elasticity_source=Route.ElasticitySource.CARGO_GROUP_AGGREGATE,
        )
    else:
        stats.cargo_group_aggregate = 0
    _report(
        progress,
        f"Разметка эластичности: cargo_group_aggregate — "
        f"{_format_route_count(stats.cargo_group_aggregate)}",
    )

    stats.skipped = operational.filter(skip_elasticity=True).count()
    _report(
        progress,
        f"Разметка эластичности: без выпадения (skip) — "
        f"{_format_route_count(stats.skipped)}",
    )
    return stats
