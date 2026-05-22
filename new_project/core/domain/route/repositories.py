from __future__ import annotations

from typing import Optional

from django.db.models import Q, QuerySet

from core.domain.route.dto import RouteListFiltersDTO, RouteWriteDTO
from core.models import Route, RouteSet


class RouteSetRepository:
    def list_queryset(self, search: Optional[str] = None) -> QuerySet[RouteSet]:
        qs = RouteSet.objects.all()
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
            "origin_station",
            "destination_station",
            "origin_station__railroad",
            "destination_station__railroad",
            "origin_station__region",
            "destination_station__region",
            "wagon_kind",
            "shipment_type",
            "message_type",
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

        return qs.order_by("id")

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
