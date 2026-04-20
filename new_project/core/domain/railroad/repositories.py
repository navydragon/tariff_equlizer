from typing import Optional

from django.db.models import Q, QuerySet

from core.models import RailRoad


class RailRoadRepository:
    def _base_queryset(self) -> QuerySet[RailRoad]:
        return RailRoad.objects.all()

    def list_filtered(
        self,
        search: Optional[str] = None,
        code: Optional[str] = None,
        name: Optional[str] = None,
        country: Optional[str] = None,
        direction: Optional[str] = None,
    ) -> QuerySet[RailRoad]:
        qs = self._base_queryset()

        if search:
            search = search.strip()
            if search:
                qs = qs.filter(
                    Q(name__icontains=search)
                    | Q(code__icontains=search)
                    | Q(country__icontains=search)
                    | Q(direction__icontains=search)
                )

        if code:
            code = code.strip()
            if code:
                qs = qs.filter(code__icontains=code)

        if name:
            name = name.strip()
            if name:
                qs = qs.filter(name__icontains=name)

        if country:
            country = country.strip()
            if country:
                qs = qs.filter(country__icontains=country)

        if direction:
            direction = direction.strip()
            if direction:
                qs = qs.filter(direction__icontains=direction)

        return qs.order_by("code")

    def get_by_code(self, code: str) -> Optional[RailRoad]:
        try:
            return self._base_queryset().get(code=code)
        except RailRoad.DoesNotExist:
            return None

    def create(self, data: dict) -> RailRoad:
        railroad = RailRoad.objects.create(**data)
        return self._base_queryset().get(code=railroad.code)

    def update(self, code: str, data: dict) -> Optional[RailRoad]:
        railroad = self.get_by_code(code)
        if not railroad:
            return None
        for key, value in data.items():
            setattr(railroad, key, value)
        railroad.save()
        return self._base_queryset().get(code=railroad.code)

    def delete(self, code: str) -> bool:
        railroad = self.get_by_code(code)
        if not railroad:
            return False
        railroad.delete()
        return True

