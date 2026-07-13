from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
from typing import Any

from core.domain.route_analysis.dto import RouteAnalysisRequestDTO

VALID_VARIANTS = frozenset({"base", "user"})


def overrides_to_api_dict(
    overrides: dict[str, dict[int, Decimal]] | None,
) -> dict[str, dict[str, str]]:
    if not overrides:
        return {}
    result: dict[str, dict[str, str]] = {}
    for type_key, year_map in overrides.items():
        result[type_key] = {
            str(year): str(value)
            for year, value in sorted(year_map.items())
        }
    return result


@dataclass(frozen=True)
class EqualizerPresetDTO:
    route_id: int
    variant: str
    overrides: dict[str, dict[str, str]]
    has_saved: bool

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "route_id": self.route_id,
            "variant": self.variant,
            "overrides": self.overrides,
            "has_saved": self.has_saved,
        }


@dataclass(frozen=True)
class SaveEqualizerPresetRequestDTO:
    route_id: int
    overrides: dict[str, dict[int, Decimal]] | None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.route_id, int) or self.route_id <= 0:
            errors.append("Некорректный route_id")
        if not self.overrides:
            errors.append("Нет значений для сохранения")
        return errors


@dataclass(frozen=True)
class SetEqualizerVariantRequestDTO:
    route_id: int
    variant: str

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.route_id, int) or self.route_id <= 0:
            errors.append("Некорректный route_id")
        if self.variant not in VALID_VARIANTS:
            errors.append("Некорректный variant")
        return errors


def parse_save_request(
    *,
    route_id: Any,
    overrides_raw: Any,
) -> tuple[SaveEqualizerPresetRequestDTO | None, list[str]]:
    try:
        parsed_route_id = int(route_id)
    except (TypeError, ValueError):
        return None, ["Некорректный route_id"]

    overrides = RouteAnalysisRequestDTO.parse_overrides(overrides_raw)
    dto = SaveEqualizerPresetRequestDTO(
        route_id=parsed_route_id,
        overrides=overrides,
    )
    errors = dto.validate()
    if errors:
        return None, errors
    return dto, []


def parse_variant_request(
    *,
    route_id: Any,
    variant: Any,
) -> tuple[SetEqualizerVariantRequestDTO | None, list[str]]:
    try:
        parsed_route_id = int(route_id)
    except (TypeError, ValueError):
        return None, ["Некорректный route_id"]

    parsed_variant = str(variant or "").strip()
    dto = SetEqualizerVariantRequestDTO(
        route_id=parsed_route_id,
        variant=parsed_variant,
    )
    errors = dto.validate()
    if errors:
        return None, errors
    return dto, []
