from __future__ import annotations

from typing import Iterable

from django.db import transaction

from calculations.domain.services.route_mart_store import bump_route_mart_refs_version
from core.domain.cargo.etsng_categories import (
    classify_cargo_flags,
    clear_cargo_category_positions_cache,
)
from core.domain.cargo_category.dto import (
    CATEGORY_LABELS,
    VALID_CATEGORIES,
    AddPositionDTO,
    CargoCategoryPositionDTO,
    CargoCategoryPositionListResultDTO,
)
from core.domain.cargo_category.repositories import CargoCategoryPositionRepository
from core.models import Cargo


class CargoCategoryService:
    def __init__(self) -> None:
        self.repository = CargoCategoryPositionRepository()

    def list_positions(
        self,
        category: str,
    ) -> tuple[CargoCategoryPositionListResultDTO | None, list[str]]:
        if category not in VALID_CATEGORIES:
            return None, ["Неизвестная категория набора"]

        cargo_counts = self.repository.cargo_counts_by_position()
        route_counts = self.repository.route_counts_by_position()
        items = [
            CargoCategoryPositionDTO(
                category=row.category,
                position=row.position,
                cargos_count=cargo_counts.get(row.position, 0),
                routes_count=route_counts.get(row.position, 0),
            )
            for row in self.repository.list_by_category(category)
        ]
        return (
            CargoCategoryPositionListResultDTO(
                items=items,
                category=category,
                category_label=CATEGORY_LABELS.get(category, category),
                total=len(items),
            ),
            [],
        )

    @transaction.atomic
    def add_position(
        self,
        dto: AddPositionDTO,
    ) -> tuple[CargoCategoryPositionDTO | None, list[str]]:
        errors = dto.validate()
        if errors:
            return None, errors

        position = dto.normalized_position
        assert position is not None

        if self.repository.exists(category=dto.category, position=position):
            return None, ["Позиция уже есть в этом наборе"]

        row = self.repository.create(category=dto.category, position=position)
        clear_cargo_category_positions_cache()
        self.reclassify_cargos({position})

        cargo_counts = self.repository.cargo_counts_by_position()
        route_counts = self.repository.route_counts_by_position()
        return (
            CargoCategoryPositionDTO(
                category=row.category,
                position=row.position,
                cargos_count=cargo_counts.get(row.position, 0),
                routes_count=route_counts.get(row.position, 0),
            ),
            [],
        )

    @transaction.atomic
    def delete_position(
        self,
        *,
        category: str,
        position: str,
    ) -> tuple[bool, list[str]]:
        from core.domain.cargo_category.dto import normalize_position

        if category not in VALID_CATEGORIES:
            return False, ["Неизвестная категория набора"]

        normalized = normalize_position(position)
        if normalized is None:
            return False, ["Позиция должна быть 3-значным числом ЕТСНГ"]

        if not self.repository.delete(category=category, position=normalized):
            return False, ["Позиция не найдена в этом наборе"]

        clear_cargo_category_positions_cache()
        self.reclassify_cargos({normalized})
        return True, []

    def reclassify_cargos(self, positions: Iterable[str]) -> int:
        position_list = list(positions)
        if not position_list:
            return 0

        cargos = list(self.repository.cargos_by_positions(position_list))
        to_update: list[Cargo] = []
        for cargo in cargos:
            is_consumer, is_food = classify_cargo_flags(cargo.code)
            if (
                cargo.is_consumer_goods != is_consumer
                or cargo.is_food_goods != is_food
            ):
                cargo.is_consumer_goods = is_consumer
                cargo.is_food_goods = is_food
                to_update.append(cargo)

        if to_update:
            Cargo.objects.bulk_update(
                to_update,
                ["is_consumer_goods", "is_food_goods"],
            )
            transaction.on_commit(bump_route_mart_refs_version)

        return len(to_update)
