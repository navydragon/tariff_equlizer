from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, NullIf

from calculations.domain.units import RUB_PER_BLN, TKM_PER_BLN, TONS_PER_MLN
from core.domain.route.repositories import RouteRepository
from core.models import RouteSet

from .dimensions import VALID_METRICS, DimensionSpec, get_dimension
from .dto import (
    METRIC_LABELS,
    RouteAnalyticsRequestDTO,
    RouteAnalyticsResultDTO,
    RouteAnalyticsRowDTO,
    RouteSetTotalCardDTO,
    RouteSetTotalsDTO,
)


def _quantize(value: Decimal, places: int = 2) -> Decimal:
    exp = Decimal("1").scaleb(-places)
    return value.quantize(exp, rounding=ROUND_HALF_UP)


def _format_pct(part: Decimal, total: Decimal) -> str:
    if total <= 0:
        return "0.0"
    pct = (part / total) * Decimal("100")
    return format(_quantize(pct, 1), "f")


def _format_count(value: Decimal) -> tuple[str, str]:
    display = str(int(value))
    return display, "шт."


def _format_money(value: Decimal) -> tuple[str, str]:
    bln = value / RUB_PER_BLN
    if bln >= Decimal("1"):
        return f"{format(_quantize(bln, 2), 'f')}", "млрд руб."
    mln = value / TONS_PER_MLN
    return f"{format(_quantize(mln, 2), 'f')}", "млн руб."


def _format_volume(value: Decimal) -> tuple[str, str]:
    mln = value / TONS_PER_MLN
    return f"{format(_quantize(mln, 2), 'f')}", "млн т"


def _format_turnover(value: Decimal) -> tuple[str, str]:
    bln = value / TKM_PER_BLN
    return f"{format(_quantize(bln, 2), 'f')}", "млрд т·км"


def _metric_formatters() -> dict[str, tuple]:
    return {
        "count": (_format_count, Count("id")),
        "money": (_format_money, Sum("freight_charge_rub")),
        "volume": (_format_volume, Sum("transport_volume_tons")),
        "turnover": (_format_turnover, Sum("freight_turnover_tkm")),
    }


def _annotate_dimension(qs, spec: DimensionSpec):
    if spec.empty_as_misc:
        return qs.annotate(
            dim_label=Case(
                When(
                    Q(**{f"{spec.orm_field}__isnull": True}) | Q(**{spec.orm_field: ""}),
                    then=Value(spec.empty_label),
                ),
                default=F(spec.orm_field),
                output_field=CharField(),
            )
        )

    return qs.annotate(
        dim_label=Coalesce(
            NullIf(F(spec.orm_field), Value("")),
            Value(spec.empty_label),
            output_field=CharField(),
        )
    )


class RouteAnalyticsService:
    def __init__(self):
        self.route_repository = RouteRepository()

    def aggregate(self, request_dto: RouteAnalyticsRequestDTO) -> tuple[RouteAnalyticsResultDTO | None, list[str]]:
        errors = request_dto.validate()
        if errors:
            return None, errors

        if not RouteSet.objects.filter(pk=request_dto.route_set_id).exists():
            return None, ["Набор маршрутов не найден"]

        spec = get_dimension(request_dto.dimension)
        assert spec is not None

        formatter, agg_expr = _metric_formatters()[request_dto.metric]

        qs = self.route_repository.list_operational_queryset(request_dto.route_set_id)
        qs = _annotate_dimension(qs, spec)

        grouped = (
            qs.values("dim_label")
            .annotate(agg_value=agg_expr)
            .order_by("-agg_value", "dim_label")
        )

        raw_rows: list[tuple[str, Decimal]] = []
        for row in grouped:
            label = str(row["dim_label"] or spec.empty_label)
            value = row["agg_value"]
            if value is None:
                value = Decimal("0")
            elif not isinstance(value, Decimal):
                value = Decimal(str(value))
            raw_rows.append((label, value))

        total = sum((value for _, value in raw_rows), start=Decimal("0"))
        total_display, unit = formatter(total)

        result_rows: list[RouteAnalyticsRowDTO] = []
        for label, value in raw_rows:
            value_display, _ = formatter(value)
            result_rows.append(
                RouteAnalyticsRowDTO(
                    label=label,
                    value=value,
                    value_display=value_display,
                    share_pct=_format_pct(value, total),
                )
            )

        result_rows.append(
            RouteAnalyticsRowDTO(
                label="ИТОГО",
                value=total,
                value_display=total_display,
                share_pct="100.0" if total > 0 else "0.0",
                is_total=True,
            )
        )

        return (
            RouteAnalyticsResultDTO(
                rows=result_rows,
                total=total,
                total_display=total_display,
                metric=request_dto.metric,
                unit=unit,
                dimension=spec.code,
                dimension_label=spec.label,
            ),
            [],
        )

    def aggregate_totals(
        self,
        route_set_id: int,
    ) -> tuple[RouteSetTotalsDTO | None, list[str]]:
        if not isinstance(route_set_id, int) or route_set_id <= 0:
            return None, ["Некорректный route_set_id"]

        try:
            route_set = RouteSet.objects.get(pk=route_set_id)
        except RouteSet.DoesNotExist:
            return None, ["Набор маршрутов не найден"]

        formatters = _metric_formatters()
        agg_kwargs = {metric: expr for metric, (_fmt, expr) in formatters.items()}
        qs = self.route_repository.list_operational_queryset(route_set_id)
        raw = qs.aggregate(**agg_kwargs)

        cards: list[RouteSetTotalCardDTO] = []
        for metric, (formatter, _expr) in formatters.items():
            value = raw.get(metric)
            if value is None:
                value = Decimal("0")
            elif not isinstance(value, Decimal):
                value = Decimal(str(value))
            value_display, unit = formatter(value)
            cards.append(
                RouteSetTotalCardDTO(
                    metric=metric,
                    label=METRIC_LABELS[metric],
                    value=value,
                    value_display=value_display,
                    unit=unit,
                )
            )

        return (
            RouteSetTotalsDTO(
                route_set_id=route_set.id,
                route_set_code=route_set.code,
                route_set_name=route_set.name,
                cards=cards,
            ),
            [],
        )
