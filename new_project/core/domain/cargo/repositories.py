"""
Репозиторий для работы с моделями справочника грузов.
Инкапсулирует работу с ORM.
"""
from typing import Optional

from django.db.models import Q, QuerySet

from core.models import Cargo, CargoGroup


class CargoRepository:
    """Репозиторий для модели Cargo."""

    def _base_queryset(self) -> QuerySet[Cargo]:
        return Cargo.objects.select_related("cargo_group").all()

    def list_filtered(
        self,
        search: Optional[str] = None,
        code: Optional[str] = None,
        name: Optional[str] = None,
        cargo_group_code: Optional[int] = None,
    ) -> QuerySet[Cargo]:
        """
        Вернуть queryset грузов с применением фильтров (без пагинации).
        """
        qs = self._base_queryset()

        if search:
            search = search.strip()
            if search:
                qs = qs.filter(
                    Q(name__icontains=search)
                    | Q(code__icontains=search)  # code — IntegerField, но Django приведёт
                )

        if code:
            code = code.strip()
            if code:
                qs = qs.filter(code__icontains=code)

        if name:
            name = name.strip()
            if name:
                qs = qs.filter(name__icontains=name)

        if cargo_group_code is not None:
            qs = qs.filter(cargo_group__code=cargo_group_code)

        return qs.order_by("code")

    def get_by_code(self, code: int) -> Optional[Cargo]:
        try:
            return self._base_queryset().get(code=code)
        except Cargo.DoesNotExist:
            return None

    def get_group_by_code(self, code: int) -> Optional[CargoGroup]:
        try:
            return CargoGroup.objects.get(code=code)
        except CargoGroup.DoesNotExist:
            return None

    def create(self, data: dict) -> Cargo:
        cargo = Cargo.objects.create(**data)
        return self._base_queryset().get(code=cargo.code)

    def update(self, code: int, data: dict) -> Optional[Cargo]:
        cargo = self.get_by_code(code)
        if not cargo:
            return None
        for key, value in data.items():
            setattr(cargo, key, value)
        cargo.save()
        return self._base_queryset().get(code=cargo.code)

    def delete(self, code: int) -> bool:
        cargo = self.get_by_code(code)
        if not cargo:
            return False
        cargo.delete()
        return True

