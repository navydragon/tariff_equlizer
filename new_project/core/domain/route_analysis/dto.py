from __future__ import annotations

from dataclasses import dataclass, field
from decimal import Decimal, InvalidOperation
from typing import Any

EQUALIZER_OVERRIDE_KEYS = frozenset(
    {"cost", "oper", "per", "price_rub", "fx", "base", "rules"},
)


@dataclass(frozen=True)
class RouteAnalysisRequestDTO:
    scenario_id: int
    route_id: int
    overrides: dict[str, dict[int, Decimal]] | None = None

    def validate(self) -> list[str]:
        errors: list[str] = []
        if not isinstance(self.scenario_id, int) or self.scenario_id <= 0:
            errors.append("Некорректный scenario_id")
        if not isinstance(self.route_id, int) or self.route_id <= 0:
            errors.append("Некорректный route_id")
        if self.overrides is not None:
            if not isinstance(self.overrides, dict):
                errors.append("overrides должен быть объектом")
            else:
                for type_key, year_map in self.overrides.items():
                    if type_key not in EQUALIZER_OVERRIDE_KEYS:
                        errors.append(f"Недопустимый ключ overrides: {type_key}")
                        continue
                    if not isinstance(year_map, dict):
                        errors.append(f"overrides[{type_key}] должен быть объектом по годам")
                        continue
                    for year, value in year_map.items():
                        if not isinstance(year, int):
                            errors.append(
                                f"Некорректный год в overrides[{type_key}]: {year}",
                            )
                            continue
                        if not isinstance(value, Decimal):
                            errors.append(
                                f"Некорректное значение overrides[{type_key}][{year}]",
                            )
        return errors

    @staticmethod
    def parse_overrides(raw: Any) -> dict[str, dict[int, Decimal]] | None:
        if raw is None:
            return None
        if not isinstance(raw, dict):
            return None
        if not raw:
            return None

        parsed: dict[str, dict[int, Decimal]] = {}
        for type_key, year_map in raw.items():
            if type_key not in EQUALIZER_OVERRIDE_KEYS:
                continue
            if not isinstance(year_map, dict):
                continue
            type_values: dict[int, Decimal] = {}
            for year_key, value in year_map.items():
                try:
                    year = int(year_key)
                except (TypeError, ValueError):
                    continue
                try:
                    type_values[year] = Decimal(str(value).replace(",", "."))
                except (InvalidOperation, ValueError):
                    continue
            if type_values:
                parsed[type_key] = type_values
        return parsed or None


@dataclass(frozen=True)
class RouteAnalysisTableRowDTO:
    key: str
    label: str
    values: Any
    format: str


@dataclass(frozen=True)
class EqualizerTypeDTO:
    key: str
    label: str
    unit: str
    step: str
    values: dict[str, str]
    visible: bool = True
    editable: bool = True
    notice: str = ""

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "unit": self.unit,
            "step": self.step,
            "values": self.values,
            "visible": self.visible,
            "editable": self.editable,
            "notice": self.notice,
        }


@dataclass(frozen=True)
class EqualizerResponseDTO:
    types: list[EqualizerTypeDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {"types": [item.to_api_dict() for item in self.types]}


@dataclass(frozen=True)
class EffectYearValueDTO:
    rub: str
    pct: str

    def to_api_dict(self) -> dict[str, str]:
        return {"rub": self.rub, "pct": self.pct}


@dataclass(frozen=True)
class EffectRowDTO:
    key: str
    label: str
    values_by_year: dict[str, EffectYearValueDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "key": self.key,
            "label": self.label,
            "values": {
                year: cell.to_api_dict()
                for year, cell in self.values_by_year.items()
            },
        }


@dataclass(frozen=True)
class EffectsResponseDTO:
    rows: list[EffectRowDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {"rows": [row.to_api_dict() for row in self.rows]}


@dataclass(frozen=True)
class TransportStructureDTO:
    show_empty_leg: bool
    rzd_loaded_by_year: dict[str, str]
    rzd_empty_by_year: dict[str, str]
    transport_pct_by_year: dict[str, str]
    marginality_pct_by_year: dict[str, str]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "show_empty_leg": self.show_empty_leg,
            "rzd_loaded_by_year": self.rzd_loaded_by_year,
            "rzd_empty_by_year": self.rzd_empty_by_year,
            "transport_pct_by_year": self.transport_pct_by_year,
            "marginality_pct_by_year": self.marginality_pct_by_year,
        }


@dataclass(frozen=True)
class KpiMetricDTO:
    label: str
    rub: str | None
    pct: str | None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "label": self.label,
            "rub": self.rub,
            "pct": self.pct,
        }


@dataclass(frozen=True)
class KpiYearDTO:
    year: int
    transport: KpiMetricDTO
    rzd: KpiMetricDTO
    marginality: KpiMetricDTO
    volume_share: KpiMetricDTO
    elasticity: KpiMetricDTO

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "year": self.year,
            "transport": self.transport.to_api_dict(),
            "rzd": self.rzd.to_api_dict(),
            "marginality": self.marginality.to_api_dict(),
            "volume_share": self.volume_share.to_api_dict(),
            "elasticity": self.elasticity.to_api_dict(),
        }


@dataclass(frozen=True)
class KpiResponseDTO:
    by_year: list[KpiYearDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {"by_year": [item.to_api_dict() for item in self.by_year]}


@dataclass(frozen=True)
class RzdTariffSensitivityPointDTO:
    change_pct: str
    coefficient: str | None

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "change_pct": self.change_pct,
            "coefficient": self.coefficient,
        }


@dataclass(frozen=True)
class RzdTariffSensitivityResponseDTO:
    points: list[RzdTariffSensitivityPointDTO]

    def to_api_dict(self) -> dict[str, Any]:
        return {
            "points": [point.to_api_dict() for point in self.points],
        }


@dataclass(frozen=True)
class RouteAnalysisResponseDTO:
    scenario_id: int
    route_id: int
    route_code: str
    years: list[int]
    rows: list[RouteAnalysisTableRowDTO]
    equalizer: EqualizerResponseDTO = field(
        default_factory=lambda: EqualizerResponseDTO(types=[]),
    )
    transport_structure: TransportStructureDTO | None = None
    effects: EffectsResponseDTO = field(
        default_factory=lambda: EffectsResponseDTO(rows=[]),
    )
    kpi: KpiResponseDTO = field(
        default_factory=lambda: KpiResponseDTO(by_year=[]),
    )
    rzd_tariff_sensitivity: RzdTariffSensitivityResponseDTO = field(
        default_factory=lambda: RzdTariffSensitivityResponseDTO(points=[]),
    )

    def to_api_dict(self) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "scenario_id": self.scenario_id,
            "route_id": self.route_id,
            "route_code": self.route_code,
            "years": self.years,
            "rows": [
                {
                    "key": row.key,
                    "label": row.label,
                    "values": row.values,
                    "format": row.format,
                }
                for row in self.rows
            ],
            "equalizer": self.equalizer.to_api_dict(),
            "effects": self.effects.to_api_dict(),
            "kpi": self.kpi.to_api_dict(),
            "rzd_tariff_sensitivity": self.rzd_tariff_sensitivity.to_api_dict(),
        }
        if self.transport_structure is not None:
            payload["transport_structure"] = self.transport_structure.to_api_dict()
        return payload
