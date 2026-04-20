from typing import Optional, Tuple

from django.core.paginator import Paginator, EmptyPage
from django.db import transaction

from .dto import (
    RailRoadDTO,
    CreateRailRoadDTO,
    UpdateRailRoadDTO,
    RailRoadListResultDTO,
)
from .repositories import RailRoadRepository


class RailRoadService:
    def __init__(self) -> None:
        self.repository = RailRoadRepository()

    def list_railroads(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        code: Optional[str] = None,
        name: Optional[str] = None,
        country: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> Tuple[Optional[RailRoadListResultDTO], list[str]]:
        if page <= 0:
            page = 1
        if page_size <= 0:
            page_size = 20

        qs = self.repository.list_filtered(
            search=search,
            code=code,
            name=name,
            country=country,
            direction=direction,
        )

        paginator = Paginator(qs, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            page_obj = paginator.page(paginator.num_pages or 1)

        items = [RailRoadDTO.from_model(r) for r in page_obj.object_list]

        result = RailRoadListResultDTO(
            items=items,
            total=paginator.count,
            page=page_obj.number,
            page_size=page_obj.paginator.per_page,
            total_pages=paginator.num_pages,
        )
        return result, []

    def get_railroad(self, code: str) -> Tuple[Optional[RailRoadDTO], list[str]]:
        railroad = self.repository.get_by_code(code)
        if not railroad:
            return None, ["Железная дорога не найдена"]
        return RailRoadDTO.from_model(railroad), []

    @transaction.atomic
    def create_railroad(
        self,
        dto: CreateRailRoadDTO,
    ) -> Tuple[Optional[RailRoadDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        normalized_code = dto.code.strip()
        if self.repository.get_by_code(normalized_code):
            return None, [f"Железная дорога с кодом {normalized_code} уже существует"]

        data: dict = {
            "code": normalized_code,
            "name": dto.name.strip(),
            "country": (dto.country or "").strip(),
            "direction": (dto.direction or "").strip(),
        }

        railroad = self.repository.create(data)
        return RailRoadDTO.from_model(railroad), []

    @transaction.atomic
    def update_railroad(
        self,
        code: str,
        dto: UpdateRailRoadDTO,
    ) -> Tuple[Optional[RailRoadDTO], list[str]]:
        railroad = self.repository.get_by_code(code)
        if not railroad:
            return None, ["Железная дорога не найдена"]

        errors = dto.validate()
        if errors:
            return None, errors

        data: dict = {}

        if dto.name is not None:
            data["name"] = dto.name.strip()

        if dto.country is not None:
            data["country"] = dto.country.strip()

        if dto.direction is not None:
            data["direction"] = dto.direction.strip()

        updated = self.repository.update(code, data)
        if not updated:
            return None, ["Ошибка при обновлении железной дороги"]

        return RailRoadDTO.from_model(updated), []

    @transaction.atomic
    def delete_railroad(self, code: str) -> Tuple[bool, list[str]]:
        success = self.repository.delete(code)
        if not success:
            return False, ["Железная дорога не найдена"]
        return True, []

