from __future__ import annotations

from collections import defaultdict
from decimal import Decimal, ROUND_HALF_UP

from django.db.models import Case, CharField, Count, F, Q, Sum, Value, When
from django.db.models.functions import Coalesce, NullIf

from calculations.domain.units import RUB_PER_BLN, TKM_PER_BLN, TONS_PER_MLN
from core.domain.route.repositories import RouteRepository
from core.models import RouteSet

from .dimensions import (
    INNER_DIMENSION_NONE,
    KPI_FIELDS_BY_YEAR,
    LOADING_BASE_YEAR,
    VALID_KPI_YEARS,
    DimensionSpec,
    get_dimension,
)
from .dto import (
    METRIC_LABELS,
    RouteAnalyticsNestedResultDTO,
    RouteAnalyticsNestedRowDTO,
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


def _metric_formatters(kpi_year: int = LOADING_BASE_YEAR) -> dict[str, tuple]:
    fields = KPI_FIELDS_BY_YEAR[kpi_year]
    return {
        "count": (_format_count, Count("id")),
        "money": (_format_money, Sum(fields["money"])),
        "volume": (_format_volume, Sum(fields["volume"])),
        "turnover": (_format_turnover, Sum(fields["turnover"])),
    }


def _to_decimal(value) -> Decimal:
    if value is None:
        return Decimal("0")
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _annotate_dimension(qs, spec: DimensionSpec, *, alias: str = "dim_label"):
    if spec.empty_as_misc:
        return qs.annotate(
            **{
                alias: Case(
                    When(
                        Q(**{f"{spec.orm_field}__isnull": True}) | Q(**{spec.orm_field: ""}),
                        then=Value(spec.empty_label),
                    ),
                    default=F(spec.orm_field),
                    output_field=CharField(),
                )
            }
        )

    return qs.annotate(
        **{
            alias: Coalesce(
                NullIf(F(spec.orm_field), Value("")),
                Value(spec.empty_label),
                output_field=CharField(),
            )
        }
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

        outer_spec = get_dimension(request_dto.dimension)
        assert outer_spec is not None

        inner_spec = None
        if request_dto.dimension_inner != INNER_DIMENSION_NONE:
            inner_spec = get_dimension(request_dto.dimension_inner)
            assert inner_spec is not None

        formatter, agg_expr = _metric_formatters(request_dto.kpi_year)[request_dto.metric]

        qs = self.route_repository.list_operational_queryset(request_dto.route_set_id)

        parent_filter = (request_dto.parent_filter or "").strip() or None
        if parent_filter is not None:
            assert inner_spec is not None
            qs = _annotate_dimension(qs, outer_spec, alias="outer_label")
            qs = qs.filter(outer_label=parent_filter)
            qs = _annotate_dimension(qs, inner_spec, alias="dim_label")
            group_spec = inner_spec
        else:
            qs = _annotate_dimension(qs, outer_spec, alias="dim_label")
            group_spec = outer_spec

        grouped = (
            qs.values("dim_label")
            .annotate(agg_value=agg_expr)
            .order_by("-agg_value", "dim_label")
        )

        raw_rows: list[tuple[str, Decimal]] = []
        for row in grouped:
            label = str(row["dim_label"] or group_spec.empty_label)
            raw_rows.append((label, _to_decimal(row["agg_value"])))

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

        drilldown_enabled = (
            inner_spec is not None and parent_filter is None
        )

        return (
            RouteAnalyticsResultDTO(
                rows=result_rows,
                total=total,
                total_display=total_display,
                metric=request_dto.metric,
                unit=unit,
                dimension=outer_spec.code if parent_filter is None else inner_spec.code,
                dimension_label=(
                    outer_spec.label if parent_filter is None else inner_spec.label
                ),
                dimension_inner=request_dto.dimension_inner,
                dimension_inner_label=inner_spec.label if inner_spec else None,
                drilldown_enabled=drilldown_enabled,
                parent_filter=parent_filter,
                parent_label=parent_filter,
            ),
            [],
        )

    def aggregate_nested(
        self,
        request_dto: RouteAnalyticsRequestDTO,
    ) -> tuple[RouteAnalyticsNestedResultDTO | None, list[str]]:
        errors = request_dto.validate()
        if errors:
            return None, errors

        if request_dto.dimension_inner == INNER_DIMENSION_NONE:
            return None, ["Группировка внутри обязательна для вложенной агрегации"]

        if not RouteSet.objects.filter(pk=request_dto.route_set_id).exists():
            return None, ["Набор маршрутов не найден"]

        outer_spec = get_dimension(request_dto.dimension)
        inner_spec = get_dimension(request_dto.dimension_inner)
        assert outer_spec is not None
        assert inner_spec is not None

        formatter, agg_expr = _metric_formatters(request_dto.kpi_year)[request_dto.metric]

        qs = self.route_repository.list_operational_queryset(request_dto.route_set_id)
        qs = _annotate_dimension(qs, outer_spec, alias="outer_label")
        qs = _annotate_dimension(qs, inner_spec, alias="inner_label")

        grouped = (
            qs.values("outer_label", "inner_label")
            .annotate(agg_value=agg_expr)
            .order_by("outer_label", "-agg_value", "inner_label")
        )

        by_outer: dict[str, list[tuple[str, Decimal]]] = defaultdict(list)
        outer_totals: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))

        for row in grouped:
            outer = str(row["outer_label"] or outer_spec.empty_label)
            inner = str(row["inner_label"] or inner_spec.empty_label)
            value = _to_decimal(row["agg_value"])
            by_outer[outer].append((inner, value))
            outer_totals[outer] += value

        grand_total = sum(outer_totals.values(), start=Decimal("0"))
        total_display, unit = formatter(grand_total)

        sorted_outers = sorted(
            outer_totals.keys(),
            key=lambda label: (-outer_totals[label], label),
        )

        result_rows: list[RouteAnalyticsNestedRowDTO] = []
        for outer in sorted_outers:
            inner_rows = sorted(by_outer[outer], key=lambda item: (-item[1], item[0]))
            for inner, value in inner_rows:
                value_display, _ = formatter(value)
                result_rows.append(
                    RouteAnalyticsNestedRowDTO(
                        outer_label=outer,
                        inner_label=inner,
                        value=value,
                        value_display=value_display,
                        share_pct=_format_pct(value, grand_total),
                    )
                )

            subtotal = outer_totals[outer]
            subtotal_display, _ = formatter(subtotal)
            result_rows.append(
                RouteAnalyticsNestedRowDTO(
                    outer_label=outer,
                    inner_label="ИТОГО",
                    value=subtotal,
                    value_display=subtotal_display,
                    share_pct=_format_pct(subtotal, grand_total),
                    is_subtotal=True,
                )
            )

        result_rows.append(
            RouteAnalyticsNestedRowDTO(
                outer_label="ИТОГО",
                inner_label="",
                value=grand_total,
                value_display=total_display,
                share_pct="100.0" if grand_total > 0 else "0.0",
                is_total=True,
            )
        )

        return (
            RouteAnalyticsNestedResultDTO(
                rows=result_rows,
                total=grand_total,
                total_display=total_display,
                metric=request_dto.metric,
                unit=unit,
                dimension=outer_spec.code,
                dimension_label=outer_spec.label,
                dimension_inner=inner_spec.code,
                dimension_inner_label=inner_spec.label,
            ),
            [],
        )

    def aggregate_totals(
        self,
        route_set_id: int,
        *,
        kpi_year: int = LOADING_BASE_YEAR,
    ) -> tuple[RouteSetTotalsDTO | None, list[str]]:
        if not isinstance(route_set_id, int) or route_set_id <= 0:
            return None, ["Некорректный route_set_id"]
        if kpi_year not in VALID_KPI_YEARS:
            return None, ["Некорректный kpi_year"]

        try:
            route_set = RouteSet.objects.get(pk=route_set_id)
        except RouteSet.DoesNotExist:
            return None, ["Набор маршрутов не найден"]

        formatters = _metric_formatters(kpi_year)
        agg_kwargs = {metric: expr for metric, (_fmt, expr) in formatters.items()}
        qs = self.route_repository.list_operational_queryset(route_set_id)
        raw = qs.aggregate(**agg_kwargs)

        cards: list[RouteSetTotalCardDTO] = []
        for metric, (formatter, _expr) in formatters.items():
            value = _to_decimal(raw.get(metric))
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
