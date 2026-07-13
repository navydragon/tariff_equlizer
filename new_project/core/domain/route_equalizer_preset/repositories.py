from __future__ import annotations

from typing import Any

from core.models import RouteEqualizerPreset


class RouteEqualizerPresetRepository:
    def get_by_user_route(
        self,
        *,
        user_id: int,
        route_id: int,
    ) -> RouteEqualizerPreset | None:
        return RouteEqualizerPreset.objects.filter(
            user_id=user_id,
            route_id=route_id,
        ).first()

    def upsert(
        self,
        *,
        user_id: int,
        route_id: int,
        variant: str,
        overrides: dict[str, Any],
    ) -> RouteEqualizerPreset:
        preset, _created = RouteEqualizerPreset.objects.update_or_create(
            user_id=user_id,
            route_id=route_id,
            defaults={
                "variant": variant,
                "overrides": overrides,
            },
        )
        return preset

    def set_variant(
        self,
        *,
        user_id: int,
        route_id: int,
        variant: str,
    ) -> RouteEqualizerPreset | None:
        preset = self.get_by_user_route(user_id=user_id, route_id=route_id)
        if preset is None:
            if variant == RouteEqualizerPreset.Variant.BASE:
                return RouteEqualizerPreset.objects.create(
                    user_id=user_id,
                    route_id=route_id,
                    variant=variant,
                    overrides={},
                )
            return None
        preset.variant = variant
        preset.save(update_fields=["variant", "updated_at"])
        return preset
