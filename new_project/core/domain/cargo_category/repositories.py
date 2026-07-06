from __future__ import annotations

from typing import Iterable

from django.db.models import Count, QuerySet
from django.db.models.functions import Substr

from core.models import Cargo, CargoCategoryPosition, Route


class CargoCategoryPositionRepository:
    def list_by_category(self, category: str) -> QuerySet[CargoCategoryPosition]:
        return CargoCategoryPosition.objects.filter(category=category).order_by("position")

    def exists(self, *, category: str, position: str) -> bool:
        return CargoCategoryPosition.objects.filter(
            category=category,
            position=position,
        ).exists()

    def create(self, *, category: str, position: str) -> CargoCategoryPosition:
        return CargoCategoryPosition.objects.create(
            category=category,
            position=position,
        )

    def delete(self, *, category: str, position: str) -> bool:
        deleted, _ = CargoCategoryPosition.objects.filter(
            category=category,
            position=position,
        ).delete()
        return deleted > 0

    def cargos_by_positions(self, positions: Iterable[str]) -> QuerySet[Cargo]:
        position_list = list(positions)
        if not position_list:
            return Cargo.objects.none()
        return Cargo.objects.annotate(
            pos=Substr("code", 1, 3),
        ).filter(pos__in=position_list)

    def cargo_counts_by_position(self) -> dict[str, int]:
        rows = (
            Cargo.objects.annotate(pos=Substr("code", 1, 3))
            .values("pos")
            .annotate(cnt=Count("pk"))
        )
        return {row["pos"]: row["cnt"] for row in rows if row["pos"]}

    def route_counts_by_position(self) -> dict[str, int]:
        rows = (
            Route.objects.filter(cargo__isnull=False)
            .annotate(pos=Substr("cargo__code", 1, 3))
            .values("pos")
            .annotate(cnt=Count("pk"))
        )
        return {row["pos"]: row["cnt"] for row in rows if row["pos"]}
