from __future__ import annotations

from decimal import Decimal, ROUND_HALF_UP

import numpy as np

from calculations.domain.dto.scenario_absolute import (
    AbsoluteTableRowDTO,
    ScenarioAbsoluteRequestDTO,
    ScenarioAbsoluteResponseDTO,
)
from calculations.domain.services.grouping import aggregate_by_groups
from calculations.domain.services.scenario_effects_compact import (
    aggregate_compact_value,
    aggregate_compact_year_values,
)
from calculations.domain.services.scenario_effects_cache import (
    ScenarioEffectsCachePayload,
    get_payload,
    validate_cache_access,
)
from scenarios.models import Scenario

_BLN_DIVISOR = Decimal("1000000")
_VOLUME_QUANT = Decimal("0.01")
_BLN_QUANT = Decimal("0.01")


class ScenarioAbsoluteService:
    def aggregate_revenues(
        self,
        *,
        scenario: Scenario,
        user_id: int,
        request: ScenarioAbsoluteRequestDTO,
    ) -> tuple[ScenarioAbsoluteResponseDTO | None, list[str]]:
        payload, errors = self._load_payload(
            cache_key=request.cache_key,
            user_id=user_id,
            scenario_id=scenario.id,
        )
        if errors:
            return None, errors

        year_values = self._aggregate_year_values(
            payload,
            request=request,
            value_fn=lambda fact, year: fact.charge_by_year.get(year, Decimal("0")),
            values_matrix=payload.compact.charge_by_year if payload.compact else None,
        )
        rows = self._format_rows(
            year_values,
            years=payload.years,
            group_by_inner=request.group_by_inner,
            format_value=_format_bln,
        )

        return (
            ScenarioAbsoluteResponseDTO(
                years=payload.years,
                total_column_label=_total_label(payload.years),
                unit="млрд руб.",
                rows=rows,
            ),
            [],
        )

    def aggregate_volumes(
        self,
        *,
        scenario: Scenario,
        user_id: int,
        request: ScenarioAbsoluteRequestDTO,
    ) -> tuple[ScenarioAbsoluteResponseDTO | None, list[str]]:
        payload, errors = self._load_payload(
            cache_key=request.cache_key,
            user_id=user_id,
            scenario_id=scenario.id,
        )
        if errors:
            return None, errors

        if payload.compact is not None:
            volume_buckets = aggregate_compact_value(
                payload.compact,
                values=payload.compact.volume_mln_tons,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                cargo_groups=[],
                holdings=[],
            )
            year_values = {
                key: {year: volume for year in payload.years}
                for key, volume in volume_buckets.items()
            }
        else:
            volume_buckets = aggregate_by_groups(
                payload.facts,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                value_fn=lambda fact: fact.volume_mln_tons,
            )
            year_values = {
                key: {year: volume for year in payload.years}
                for key, volume in volume_buckets.items()
            }

        rows = self._format_rows(
            year_values,
            years=payload.years,
            group_by_inner=request.group_by_inner,
            format_value=_format_volume,
        )

        return (
            ScenarioAbsoluteResponseDTO(
                years=payload.years,
                total_column_label=_total_label(payload.years),
                unit="млн т",
                rows=rows,
            ),
            [],
        )

    def _load_payload(
        self,
        *,
        cache_key: str,
        user_id: int,
        scenario_id: int,
    ) -> tuple[ScenarioEffectsCachePayload | None, list[str]]:
        payload = get_payload(cache_key)
        if payload is None:
            return None, ["Расчёт устарел. Выберите сценарий заново."]

        access_errors = validate_cache_access(
            payload=payload,
            user_id=user_id,
            scenario_id=scenario_id,
        )
        if access_errors:
            return None, access_errors

        return payload, []

    def _aggregate_year_values(
        self,
        payload: ScenarioEffectsCachePayload,
        *,
        request: ScenarioAbsoluteRequestDTO,
        value_fn,
        values_matrix: np.ndarray | None = None,
    ) -> dict[tuple[str, ...], dict[int, Decimal]]:
        if payload.compact is not None and values_matrix is not None:
            return aggregate_compact_year_values(
                payload.compact,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                cargo_groups=[],
                holdings=[],
                values_by_year=values_matrix,
            )

        year_values: dict[tuple[str, ...], dict[int, Decimal]] = {}
        for year in payload.years:
            year_buckets = aggregate_by_groups(
                payload.facts,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                value_fn=lambda fact, y=year: value_fn(fact, y),
            )
            for key, value in year_buckets.items():
                if key not in year_values:
                    year_values[key] = {}
                year_values[key][year] = value
        return year_values

    def _format_rows(
        self,
        year_values: dict[tuple[str, ...], dict[int, Decimal]],
        *,
        years: list[int],
        group_by_inner: str,
        format_value,
    ) -> list[AbsoluteTableRowDTO]:
        rows: list[AbsoluteTableRowDTO] = []

        grand_years: dict[int, Decimal] = {year: Decimal("0") for year in years}
        for key, values in year_values.items():
            if group_by_inner != "none":
                if len(key) != 2 or key[1] != "ИТОГО":
                    continue
            elif len(key) != 1:
                continue
            for year in years:
                grand_years[year] += values.get(year, Decimal("0"))

        rows.append(
            _row_from_values(
                "ИТОГО",
                grand_years,
                years=years,
                format_value=format_value,
                is_subtotal=True,
            ),
        )

        if group_by_inner == "none":
            keys = sorted(
                (key for key in year_values if len(key) == 1),
                key=lambda k: sum(year_values[k].values(), Decimal("0")),
                reverse=True,
            )
            for key in keys:
                rows.append(
                    _row_from_values(
                        key[0],
                        year_values[key],
                        years=years,
                        format_value=format_value,
                        is_subtotal=False,
                    ),
                )
            return rows

        outers = sorted({key[0] for key in year_values if len(key) == 2})
        for outer in outers:
            subtotal_key = (outer, "ИТОГО")
            if subtotal_key in year_values:
                rows.append(
                    _row_from_values(
                        outer,
                        year_values[subtotal_key],
                        years=years,
                        format_value=format_value,
                        is_subtotal=True,
                    ),
                )

            inner_keys = sorted(
                (
                    key
                    for key in year_values
                    if len(key) == 2 and key[0] == outer and key[1] != "ИТОГО"
                ),
                key=lambda k: sum(year_values[k].values(), Decimal("0")),
                reverse=True,
            )
            for key in inner_keys:
                rows.append(
                    _row_from_values(
                        f"  {key[1]}",
                        year_values[key],
                        years=years,
                        format_value=format_value,
                        is_subtotal=False,
                    ),
                )

        return rows


def _row_from_values(
    label: str,
    values: dict[int, Decimal],
    *,
    years: list[int],
    format_value,
    is_subtotal: bool,
) -> AbsoluteTableRowDTO:
    year_str = {
        str(year): format_value(values.get(year, Decimal("0"))) for year in years
    }
    total = sum((values.get(year, Decimal("0")) for year in years), Decimal("0"))
    return AbsoluteTableRowDTO(
        label=label,
        is_subtotal=is_subtotal,
        years=year_str,
        total=format_value(total),
    )


def _format_bln(value: Decimal) -> str:
    bln = (value / _BLN_DIVISOR).quantize(_BLN_QUANT, rounding=ROUND_HALF_UP)
    return format(bln, "f")


def _format_volume(value: Decimal) -> str:
    return format(value.quantize(_VOLUME_QUANT, rounding=ROUND_HALF_UP), "f")


def _total_label(years: list[int]) -> str:
    if not years:
        return "Итого"
    return f"{years[0]}-{years[-1]}"
