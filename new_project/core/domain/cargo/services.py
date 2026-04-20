"""
Сервисы для бизнес-логики справочника грузов.
Работают поверх репозитория и DTO.
"""
from typing import Optional, Tuple

from django.core.paginator import Paginator, EmptyPage
from django.db import transaction

from .dto import (
    CargoDTO,
    CreateCargoDTO,
    UpdateCargoDTO,
    CargoListResultDTO,
)
from .repositories import CargoRepository


class CargoService:
    """Сервис для работы с грузами (Cargo)."""

    def __init__(self) -> None:
        self.repository = CargoRepository()

    def list_cargos(
        self,
        page: int = 1,
        page_size: int = 20,
        search: Optional[str] = None,
        code: Optional[str] = None,
        name: Optional[str] = None,
        cargo_group_code: Optional[int] = None,
    ) -> Tuple[Optional[CargoListResultDTO], list[str]]:
        """
        Вернуть постраничный список грузов с фильтрами и поиском.
        """
        if page <= 0:
            page = 1
        if page_size <= 0:
            page_size = 20

        # Сначала применяем структурные фильтры (код, имя, группа) на уровне БД.
        base_qs = self.repository.list_filtered(
            search=None,
            code=code,
            name=name,
            cargo_group_code=cargo_group_code,
        )

        # Поисковый текст обрабатываем регистронезависимо на стороне Python,
        # чтобы одинаково работать с кириллицей независимо от настроек БД.
        if search:
            s = search.strip()
            if s:
                needle = s.casefold()
                objects = [
                    c
                    for c in base_qs
                    if needle in (c.name or "").casefold()
                    or needle in str(c.code)
                ]
            else:
                objects = list(base_qs)
        else:
            objects = list(base_qs)

        paginator = Paginator(objects, page_size)
        try:
            page_obj = paginator.page(page)
        except EmptyPage:
            # Если страница вне диапазона — возвращаем последнюю страницу.
            page_obj = paginator.page(paginator.num_pages or 1)

        items = [CargoDTO.from_model(c) for c in page_obj.object_list]

        result = CargoListResultDTO(
            items=items,
            total=paginator.count,
            page=page_obj.number,
            page_size=page_obj.paginator.per_page,
            total_pages=paginator.num_pages,
        )
        return result, []

    def get_cargo(self, code: int) -> Tuple[Optional[CargoDTO], list[str]]:
        cargo = self.repository.get_by_code(code)
        if not cargo:
            return None, ["Груз не найден"]
        return CargoDTO.from_model(cargo), []

    @transaction.atomic
    def create_cargo(
        self,
        dto: CreateCargoDTO,
    ) -> Tuple[Optional[CargoDTO], list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        # Проверяем уникальность кода
        if self.repository.get_by_code(dto.code):
            return None, [f"Груз с кодом {dto.code} уже существует"]

        group = None
        if dto.cargo_group_code is not None:
            group = self.repository.get_group_by_code(dto.cargo_group_code)
            if not group:
                return None, ["Указана несуществующая группа груза"]

        data: dict = {
            "code": dto.code,
            "name": dto.name.strip(),
            "cargo_group": group,
        }

        cargo = self.repository.create(data)
        return CargoDTO.from_model(cargo), []

    @transaction.atomic
    def update_cargo(
        self,
        code: int,
        dto: UpdateCargoDTO,
    ) -> Tuple[Optional[CargoDTO], list[str]]:
        cargo = self.repository.get_by_code(code)
        if not cargo:
            return None, ["Груз не найден"]

        errors = dto.validate()
        if errors:
            return None, errors

        data: dict = {}

        if dto.name is not None:
            data["name"] = dto.name.strip()

        if dto.cargo_group_code is not None:
            if dto.cargo_group_code == 0:
                data["cargo_group"] = None
            else:
                group = self.repository.get_group_by_code(dto.cargo_group_code)
                if not group:
                    return None, ["Указана несуществующая группа груза"]
                data["cargo_group"] = group

        updated = self.repository.update(code, data)
        if not updated:
            return None, ["Ошибка при обновлении груза"]

        return CargoDTO.from_model(updated), []

    @transaction.atomic
    def delete_cargo(self, code: int) -> Tuple[bool, list[str]]:
        success = self.repository.delete(code)
        if not success:
            return False, ["Груз не найден"]
        return True, []

