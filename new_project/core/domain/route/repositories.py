from __future__ import annotations

from typing import Optional

from django.db.models import Count, Q, QuerySet

from core.domain.cargo.formatting import format_etsng_code
from core.domain.cargo.ordering import sort_cargo_group_names
from core.domain.route.dto import (
    RouteListFiltersDTO,
    RoutePickerOptionDTO,
    RoutePickerOptionsRequestDTO,
    RouteWriteDTO,
)
from core.models import Route, RouteSet


class RouteSetRepository:
    def list_queryset(
        self,
        search: Optional[str] = None,
        *,
        include_routes_count: bool = True,
    ) -> QuerySet[RouteSet]:
        qs = RouteSet.objects.all()
        if include_routes_count:
            qs = qs.annotate(_routes_count=Count("routes"))
        if search:
            search = search.strip()
            if search:
                qs = qs.filter(Q(name__icontains=search) | Q(code__icontains=search))
        return qs.order_by("name")

    def get_by_id(self, pk: int) -> Optional[RouteSet]:
        try:
            return RouteSet.objects.get(pk=pk)
        except RouteSet.DoesNotExist:
            return None

    def exists_by_name(self, name: str, *, exclude_pk: Optional[int] = None) -> bool:
        qs = RouteSet.objects.filter(name=name)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    def exists_by_code(self, code: str, *, exclude_pk: Optional[int] = None) -> bool:
        qs = RouteSet.objects.filter(code=code)
        if exclude_pk is not None:
            qs = qs.exclude(pk=exclude_pk)
        return qs.exists()

    def create(self, *, name: str, code: str) -> RouteSet:
        return RouteSet.objects.create(name=name, code=code)

    def save(self, route_set: RouteSet) -> RouteSet:
        route_set.save()
        return route_set

    def delete(self, route_set: RouteSet) -> None:
        route_set.delete()

    def routes_count(self, route_set_id: int) -> int:
        return Route.objects.filter(route_set_id=route_set_id).count()


class RouteRepository:
    def detail_queryset(self) -> QuerySet[Route]:
        return Route.objects.select_related(
            "route_set",
            "cargo",
            "cargo__cargo_group",
            "origin_station",
            "destination_station",
            "origin_station__railroad",
            "destination_station__railroad",
            "origin_station__region",
            "destination_station__region",
            "wagon_kind",
            "shipment_type",
            "message_type",
            "shipper",
            "model_route",
        )

    def list_queryset(self, route_set_id: int) -> QuerySet[Route]:
        return self.detail_queryset().filter(route_set_id=route_set_id)

    def apply_filters(
        self,
        qs: QuerySet[Route],
        filters: RouteListFiltersDTO,
    ) -> QuerySet[Route]:
        search = filters.search or ""
        if search:
            search = search.strip()
            if search:
                qs = qs.filter(self._build_search_query(search))

        if filters.origin_esr:
            qs = qs.filter(origin_station__esr_code=int(filters.origin_esr))

        if filters.destination_esr:
            qs = qs.filter(destination_station__esr_code=int(filters.destination_esr))

        if filters.economics_filled or filters.is_model_only:
            qs = qs.filter(is_model=True)

        qs = self._apply_picker_parents(
            qs,
            cargo_group_name=filters.cargo_group_name,
            cargo_code=filters.cargo_code,
            message_type_name=filters.message_type_name,
            holding=filters.holding,
        )

        return qs.order_by("id")

    @staticmethod
    def _base_picker_qs(route_set_id: int, *, economics_filled: bool) -> QuerySet[Route]:
        qs = Route.objects.filter(route_set_id=route_set_id)
        if economics_filled:
            qs = qs.filter(is_model=True)
        return qs

    @staticmethod
    def _apply_picker_parents(
        qs: QuerySet[Route],
        *,
        cargo_group_name: str | None = None,
        cargo_code: str | None = None,
        message_type_name: str | None = None,
        holding: str | None = None,
    ) -> QuerySet[Route]:
        if cargo_group_name:
            qs = qs.filter(cargo__cargo_group__name=cargo_group_name)
        if cargo_code:
            qs = qs.filter(cargo_id=cargo_code)
        if message_type_name:
            qs = qs.filter(message_type__name=message_type_name)
        if holding:
            qs = qs.filter(shipper__holding=holding)
        return qs

    def list_picker_options(
        self,
        request: RoutePickerOptionsRequestDTO,
    ) -> list[RoutePickerOptionDTO]:
        qs = self._base_picker_qs(
            request.route_set_id,
            economics_filled=request.economics_filled,
        )
        qs = self._apply_picker_parents(
            qs,
            cargo_group_name=request.cargo_group_name,
            cargo_code=request.cargo_code,
            message_type_name=request.message_type_name,
            holding=request.holding,
        )
        search = (request.search or "").strip() or None
        limit = min(max(request.limit, 1), 100)

        if request.dimension == "cargo_group":
            qs = qs.exclude(cargo__cargo_group__name__isnull=True).exclude(
                cargo__cargo_group__name="",
            )
            if search:
                qs = qs.filter(
                    cargo__cargo_group__name_search__contains=search.casefold(),
                )
            names = {
                name
                for name in qs.values_list("cargo__cargo_group__name", flat=True).distinct()
                if name
            }
            return [
                RoutePickerOptionDTO(value=name, text=name)
                for name in sort_cargo_group_names(names)[:limit]
            ]

        if request.dimension == "cargo":
            qs = qs.exclude(cargo_id__isnull=True)
            if search:
                qs = qs.filter(
                    Q(cargo__name__icontains=search)
                    | Q(cargo__code__icontains=search),
                )
            rows = (
                qs.values("cargo_id", "cargo__code", "cargo__name")
                .distinct()
                .order_by("cargo__code")[:limit]
            )
            items: list[RoutePickerOptionDTO] = []
            for row in rows:
                code = format_etsng_code(row["cargo__code"])
                name = row["cargo__name"] or ""
                text = f"{code} — {name}" if name else code
                items.append(
                    RoutePickerOptionDTO(value=str(row["cargo_id"]), text=text),
                )
            return items

        if request.dimension == "transport_type":
            qs = qs.exclude(message_type__name__isnull=True).exclude(message_type__name="")
            if search:
                qs = qs.filter(message_type__name_search__contains=search.casefold())
            names = list(
                qs.values_list("message_type__name", flat=True)
                .distinct()
                .order_by("message_type__name")[:limit],
            )
            return [RoutePickerOptionDTO(value=name, text=name) for name in names if name]

        if request.dimension == "holding":
            qs = qs.exclude(shipper__isnull=True).exclude(shipper__holding="")
            if search:
                qs = qs.filter(shipper__holding_search__contains=search.casefold())
            names = list(
                qs.values_list("shipper__holding", flat=True)
                .distinct()
                .order_by("shipper__holding")[:limit],
            )
            return [RoutePickerOptionDTO(value=name, text=name) for name in names if name]

        return []

    def list_distinct_holdings(
        self,
        route_set_id: int,
        *,
        search: str | None = None,
        economics_filled: bool = False,
        limit: int = 50,
    ) -> list[str]:
        items = self.list_picker_options(
            RoutePickerOptionsRequestDTO(
                route_set_id=route_set_id,
                dimension="holding",
                economics_filled=economics_filled,
                search=search,
                limit=limit,
            ),
        )
        return [item.value for item in items]

    @staticmethod
    def _build_search_query(search: str) -> Q:
        """
        Поиск в модалке «Выбор маршрута» (route_list_api).
        Для кода ЕСР — отдельная ветка с индексами (route_set, origin/destination_station).
        """
        if search.isdigit():
            esr = int(search)
            return (
                Q(origin_station__esr_code=esr)
                | Q(destination_station__esr_code=esr)
                | Q(route_code__icontains=search)
            )

        s = search.casefold()
        q = (
            Q(cargo__name__icontains=search)
            | Q(cargo__cargo_group__name_search__contains=s)
            | Q(shipper__holding_search__contains=s)
            | Q(origin_station__short_name_search__contains=s)
            | Q(origin_station__full_name_search__contains=s)
            | Q(destination_station__short_name_search__contains=s)
            | Q(destination_station__full_name_search__contains=s)
            | Q(route_code__icontains=search)
            | Q(message_type__name_search__contains=s)
        )
        if " " not in search:
            q |= Q(route_code__istartswith=search)
        return q

    def get_by_id(self, pk: int) -> Optional[Route]:
        try:
            return self.detail_queryset().get(pk=pk)
        except Route.DoesNotExist:
            return None

    def get_by_id_for_update(self, pk: int) -> Optional[Route]:
        try:
            return Route.objects.get(pk=pk)
        except Route.DoesNotExist:
            return None

    def create(self, write_dto: RouteWriteDTO) -> Route:
        return Route.objects.create(**write_dto.payload)

    def update(self, route: Route, write_dto: RouteWriteDTO) -> Route:
        for field, value in write_dto.payload.items():
            setattr(route, field, value)
        route.save()
        return route

    def delete(self, route: Route) -> None:
        route.delete()
