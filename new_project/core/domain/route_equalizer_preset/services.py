from __future__ import annotations

from decimal import Decimal

from core.domain.route.repositories import RouteRepository
from core.domain.route_equalizer_preset.dto import (
    EqualizerPresetDTO,
    SaveEqualizerPresetRequestDTO,
    SetEqualizerVariantRequestDTO,
    overrides_to_api_dict,
)
from core.domain.route_equalizer_preset.repositories import (
    RouteEqualizerPresetRepository,
)
from core.models import RouteEqualizerPreset


class RouteEqualizerPresetService:
    def __init__(self) -> None:
        self.repository = RouteEqualizerPresetRepository()
        self.route_repository = RouteRepository()

    def get_preset(
        self,
        *,
        user_id: int,
        route_id: int,
    ) -> tuple[EqualizerPresetDTO | None, list[str]]:
        route_errors = self._validate_route(route_id)
        if route_errors:
            return None, route_errors

        preset = self.repository.get_by_user_route(
            user_id=user_id,
            route_id=route_id,
        )
        if preset is None:
            return (
                EqualizerPresetDTO(
                    route_id=route_id,
                    variant=RouteEqualizerPreset.Variant.BASE,
                    overrides={},
                    has_saved=False,
                ),
                [],
            )

        has_saved = bool(preset.overrides)
        variant = preset.variant
        if variant == RouteEqualizerPreset.Variant.USER and not has_saved:
            variant = RouteEqualizerPreset.Variant.BASE

        return (
            EqualizerPresetDTO(
                route_id=route_id,
                variant=variant,
                overrides=self._overrides_from_json(preset.overrides),
                has_saved=has_saved,
            ),
            [],
        )

    def save_preset(
        self,
        *,
        user_id: int,
        request_dto: SaveEqualizerPresetRequestDTO,
    ) -> tuple[EqualizerPresetDTO | None, list[str]]:
        route_errors = self._validate_route(request_dto.route_id)
        if route_errors:
            return None, route_errors

        assert request_dto.overrides is not None
        overrides_json = overrides_to_api_dict(request_dto.overrides)
        preset = self.repository.upsert(
            user_id=user_id,
            route_id=request_dto.route_id,
            variant=RouteEqualizerPreset.Variant.USER,
            overrides=overrides_json,
        )
        return (
            EqualizerPresetDTO(
                route_id=request_dto.route_id,
                variant=preset.variant,
                overrides=self._overrides_from_json(preset.overrides),
                has_saved=True,
            ),
            [],
        )

    def set_variant(
        self,
        *,
        user_id: int,
        request_dto: SetEqualizerVariantRequestDTO,
    ) -> tuple[EqualizerPresetDTO | None, list[str]]:
        route_errors = self._validate_route(request_dto.route_id)
        if route_errors:
            return None, route_errors

        existing = self.repository.get_by_user_route(
            user_id=user_id,
            route_id=request_dto.route_id,
        )
        if (
            request_dto.variant == RouteEqualizerPreset.Variant.USER
            and (existing is None or not existing.overrides)
        ):
            return None, ["Пользовательский вариант не сохранён"]

        preset = self.repository.set_variant(
            user_id=user_id,
            route_id=request_dto.route_id,
            variant=request_dto.variant,
        )
        if preset is None:
            return None, ["Пользовательский вариант не сохранён"]

        has_saved = bool(preset.overrides)
        variant = preset.variant
        if variant == RouteEqualizerPreset.Variant.USER and not has_saved:
            variant = RouteEqualizerPreset.Variant.BASE

        return (
            EqualizerPresetDTO(
                route_id=request_dto.route_id,
                variant=variant,
                overrides=self._overrides_from_json(preset.overrides),
                has_saved=has_saved,
            ),
            [],
        )

    def _validate_route(self, route_id: int) -> list[str]:
        route = self.route_repository.get_by_id(route_id)
        if route is None:
            return ["Маршрут не найден"]
        return []

    def _overrides_from_json(
        self,
        raw: dict | None,
    ) -> dict[str, dict[str, str]]:
        if not raw or not isinstance(raw, dict):
            return {}
        result: dict[str, dict[str, str]] = {}
        for type_key, year_map in raw.items():
            if not isinstance(year_map, dict):
                continue
            parsed_years: dict[str, str] = {}
            for year_key, value in year_map.items():
                try:
                    Decimal(str(value).replace(",", "."))
                except Exception:
                    continue
                parsed_years[str(year_key)] = str(value)
            if parsed_years:
                result[str(type_key)] = parsed_years
        return result
