from __future__ import annotations

from typing import Optional

from django.core.paginator import EmptyPage, Paginator
from django.db import transaction

from core.domain.route.dto import (
    CreateRouteSetDTO,
    RouteDTO,
    RouteListFiltersDTO,
    RouteListResultDTO,
    RouteSetDTO,
    RouteSetListResultDTO,
    RouteWriteDTO,
    UpdateRouteSetDTO,
)
from core.domain.route.repositories import RouteRepository, RouteSetRepository


class RouteSetService:
    def __init__(self) -> None:
        self.repository = RouteSetRepository()

    def list_sets(
        self,
        page: int = 1,
        page_size: int = 50,
        search: Optional[str] = None,
    ) -> tuple[Optional[RouteSetListResultDTO], list[str]]:
        if page <= 0:
            page = 1
        if page_size <= 0:
            page_size = 50

        qs = self.repository.list_queryset(search)
        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages or 1)

        items = [
            RouteSetDTO.from_model(
                rs,
                routes_count=getattr(rs, "_routes_count", None)
                if getattr(rs, "_routes_count", None) is not None
                else self.repository.routes_count(rs.id),
            )
            for rs in page_obj.object_list
        ]
        return (
            RouteSetListResultDTO(
                items=items,
                total=paginator.count,
                page=page_obj.number,
                page_size=page_obj.paginator.per_page,
                total_pages=paginator.num_pages,
            ),
            [],
        )

    def get_set(self, pk: int) -> tuple[Optional[RouteSetDTO], list[str]]:
        route_set = self.repository.get_by_id(pk)
        if not route_set:
            return None, ["Набор маршрутов не найден"]
        return (
            RouteSetDTO.from_model(
                route_set,
                routes_count=self.repository.routes_count(route_set.id),
            ),
            [],
        )

    @transaction.atomic
    def create_set(
        self,
        dto: CreateRouteSetDTO,
    ) -> tuple[Optional[RouteSetDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        name = dto.name.strip()
        code = dto.code.strip()

        if self.repository.exists_by_name(name):
            return None, ["Набор с таким названием уже существует"]
        if self.repository.exists_by_code(code):
            return None, ["Набор с таким кодом уже существует"]

        route_set = self.repository.create(name=name, code=code)
        return RouteSetDTO.from_model(route_set, routes_count=0), []

    @transaction.atomic
    def update_set(
        self,
        pk: int,
        dto: UpdateRouteSetDTO,
    ) -> tuple[Optional[RouteSetDTO], list[str]]:
        route_set = self.repository.get_by_id(pk)
        if not route_set:
            return None, ["Набор маршрутов не найден"]

        errors: list[str] = []
        name = route_set.name
        code = route_set.code

        if dto.name is not None:
            name = dto.name.strip()
            if not name:
                errors.append("Название набора обязательно")
            elif self.repository.exists_by_name(name, exclude_pk=route_set.pk):
                errors.append("Другой набор с таким названием уже существует")

        if dto.code is not None:
            code = dto.code.strip()
            if not code:
                errors.append("Код набора обязателен")
            elif self.repository.exists_by_code(code, exclude_pk=route_set.pk):
                errors.append("Другой набор с таким кодом уже существует")

        if errors:
            return None, errors

        route_set.name = name
        route_set.code = code
        self.repository.save(route_set)
        return (
            RouteSetDTO.from_model(
                route_set,
                routes_count=self.repository.routes_count(route_set.id),
            ),
            [],
        )

    @transaction.atomic
    def delete_set(self, pk: int) -> tuple[bool, list[str]]:
        route_set = self.repository.get_by_id(pk)
        if not route_set:
            return False, ["Набор маршрутов не найден"]
        self.repository.delete(route_set)
        return True, []


class RouteService:
    def __init__(self) -> None:
        self.repository = RouteRepository()

    def list_routes(
        self,
        filters: RouteListFiltersDTO,
    ) -> tuple[Optional[RouteListResultDTO], list[str]]:
        if not filters.route_set_id:
            return None, ["Не указан набор маршрутов"]

        if filters.origin_esr:
            try:
                int(filters.origin_esr)
            except (TypeError, ValueError):
                return None, ["Код ЕСР станции отправления должен быть целым числом"]

        if filters.destination_esr:
            try:
                int(filters.destination_esr)
            except (TypeError, ValueError):
                return None, ["Код ЕСР станции назначения должен быть целым числом"]

        page = filters.page if filters.page > 0 else 1
        page_size = filters.page_size if filters.page_size > 0 else 20
        page_size = min(page_size, 100)

        qs = self.repository.list_queryset(filters.route_set_id)
        qs = self.repository.apply_filters(qs, filters)

        if filters.include_total:
            paginator = Paginator(qs, page_size)
            try:
                page_obj = paginator.page(page)
            except EmptyPage:
                page_obj = paginator.page(paginator.num_pages or 1)

            items = [RouteDTO.from_model(route) for route in page_obj.object_list]
            return (
                RouteListResultDTO(
                    items=items,
                    total=paginator.count,
                    page=page_obj.number,
                    page_size=page_obj.paginator.per_page,
                    total_pages=paginator.num_pages,
                    has_next=page_obj.has_next(),
                ),
                [],
            )

        offset = (page - 1) * page_size
        chunk = list(qs[offset : offset + page_size + 1])
        has_next = len(chunk) > page_size
        page_items = chunk[:page_size]
        items = [RouteDTO.from_model(route) for route in page_items]
        return (
            RouteListResultDTO(
                items=items,
                page=page,
                page_size=page_size,
                has_next=has_next,
            ),
            [],
        )

    def get_route(self, pk: int) -> tuple[Optional[RouteDTO], list[str]]:
        route = self.repository.get_by_id(pk)
        if not route:
            return None, ["Маршрут не найден"]
        return RouteDTO.from_model(route), []

    @transaction.atomic
    def create_route(self, data: dict) -> tuple[Optional[RouteDTO], list[str]]:
        write_dto, errors = RouteWriteDTO.from_request_data(data)
        if errors:
            return None, errors
        assert write_dto is not None

        try:
            route = self.repository.create(write_dto)
        except Exception as exc:  # noqa: BLE001
            return None, [f"Не удалось создать маршрут: {exc}"]

        route = self.repository.get_by_id(route.pk)
        assert route is not None
        return RouteDTO.from_model(route), []

    @transaction.atomic
    def update_route(self, pk: int, data: dict) -> tuple[Optional[RouteDTO], list[str]]:
        route = self.repository.get_by_id_for_update(pk)
        if not route:
            return None, ["Маршрут не найден"]

        write_dto, errors = RouteWriteDTO.from_request_data(data)
        if errors:
            return None, errors
        assert write_dto is not None

        try:
            route = self.repository.update(route, write_dto)
        except Exception as exc:  # noqa: BLE001
            return None, [f"Не удалось сохранить маршрут: {exc}"]

        route = self.repository.get_by_id(route.pk)
        assert route is not None
        return RouteDTO.from_model(route), []

    @transaction.atomic
    def delete_route(self, pk: int) -> tuple[bool, list[str]]:
        route = self.repository.get_by_id_for_update(pk)
        if not route:
            return False, ["Маршрут не найден"]
        self.repository.delete(route)
        return True, []
