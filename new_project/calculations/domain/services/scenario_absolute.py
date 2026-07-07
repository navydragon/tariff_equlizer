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
    COMPACT_API_WAIT_TIMEOUT_SECONDS,
    EarlyGroupSnapshot,
    ScenarioEffectsCachePayload,
    get_payload_ready,
    validate_cache_access,
)
from calculations.domain.units import RUB_PER_BLN, TONS_PER_MLN
from core.domain.cargo.ordering import cargo_group_sort_key, sort_group_labels
from scenarios.models import Scenario

_VOLUME_QUANT = Decimal("0.01")
_BLN_QUANT = Decimal("0.01")
_ERR_FALLOUT_PENDING = (
    "Расчёт выпадения ещё выполняется. Повторите запрос через несколько секунд."
)


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
            request=request,
        )
        if errors:
            return None, errors

        if self._can_use_early_snapshot(payload, request):
            if request.include_fallout:
                return None, [_ERR_FALLOUT_PENDING]
            year_values = self._year_values_from_early_snapshot(
                payload.early_group_snapshot,
                years=payload.years,
                metric="charge",
            )
        else:
            year_values = self._aggregate_year_values(
                payload,
                request=request,
                value_fn=lambda fact, year: fact.charge_by_year.get(year, Decimal("0")),
                values_matrix=payload.compact.charge_by_year if payload.compact else None,
            )

        fallout_year_values = None
        if request.include_fallout:
            fallout_errors = self._require_fallout_arrays(
                scenario=scenario,
                payload=payload,
            )
            if fallout_errors:
                return None, fallout_errors
            assert payload.compact is not None
            fallout_year_values = aggregate_compact_year_values(
                payload.compact,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                cargo_groups=[],
                holdings=[],
                values_by_year=payload.compact.money_fallout_by_year,
            )

        rows = self._format_rows(
            year_values,
            years=payload.years,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
            format_value=_format_bln,
            fallout_year_values=fallout_year_values,
            format_fallout=_format_bln,
        )

        return (
            ScenarioAbsoluteResponseDTO(
                years=payload.years,
                total_column_label=_total_label(payload.years),
                unit="млрд руб.",
                rows=rows,
                show_fallout_adjusted=bool(fallout_year_values),
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
            request=request,
        )
        if errors:
            return None, errors

        if request.include_fallout:
            fallout_errors = self._require_fallout_arrays(
                scenario=scenario,
                payload=payload,
            )
            if fallout_errors:
                return None, fallout_errors

        if self._can_use_early_snapshot(payload, request):
            if request.include_fallout:
                return None, [_ERR_FALLOUT_PENDING]
            year_values = self._year_values_from_early_snapshot(
                payload.early_group_snapshot,
                years=payload.years,
                metric="volume",
            )
            if self._year_values_are_empty(year_values) and payload.compact is not None:
                year_values = self._aggregate_volumes_from_compact(payload, request)
        elif payload.compact is not None:
            year_values = self._aggregate_volumes_from_compact(payload, request)
        else:
            volume_buckets = aggregate_by_groups(
                payload.facts,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                value_fn=lambda fact: fact.volume_tons,
            )
            year_values = {
                key: {year: volume for year in payload.years}
                for key, volume in volume_buckets.items()
            }

        fallout_year_values = None
        if request.include_fallout:
            assert payload.compact is not None
            fallout_year_values = aggregate_compact_year_values(
                payload.compact,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                cargo_groups=[],
                holdings=[],
                values_by_year=payload.compact.volume_fallout_by_year,
            )

        rows = self._format_rows(
            year_values,
            years=payload.years,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
            format_value=_format_volume,
            fallout_year_values=fallout_year_values,
            format_fallout=_format_volume,
        )

        return (
            ScenarioAbsoluteResponseDTO(
                years=payload.years,
                total_column_label=_total_label(payload.years),
                unit="млн т",
                rows=rows,
                show_fallout_adjusted=bool(fallout_year_values),
            ),
            [],
        )

    @staticmethod
    def _require_fallout_arrays(
        *,
        scenario: Scenario,
        payload: ScenarioEffectsCachePayload,
    ) -> list[str]:
        if not scenario.consider_demand_elasticity:
            return ["У сценария не включён учёт эластичности спроса."]
        if payload.compact is None:
            if payload.compact_pending:
                return [_ERR_FALLOUT_PENDING]
            return ["Кэш расчёта устарел. Выберите сценарий заново."]
        if (
            payload.compact.volume_fallout_by_year is None
            or payload.compact.money_fallout_by_year is None
        ):
            return [_ERR_FALLOUT_PENDING]
        return []

    def _load_payload(
        self,
        *,
        cache_key: str,
        user_id: int,
        scenario_id: int,
        request: ScenarioAbsoluteRequestDTO,
    ) -> tuple[ScenarioEffectsCachePayload | None, list[str]]:
        payload = get_payload_ready(
            cache_key,
            timeout_seconds=COMPACT_API_WAIT_TIMEOUT_SECONDS,
        )
        if payload is None:
            return None, ["Расчёт устарел. Выберите сценарий заново."]

        access_errors = validate_cache_access(
            payload=payload,
            user_id=user_id,
            scenario_id=scenario_id,
        )
        if access_errors:
            return None, access_errors

        if payload.compact is None and payload.compact_pending:
            if request.include_fallout:
                return None, [_ERR_FALLOUT_PENDING]
            if self._can_use_early_snapshot(payload, request):
                return payload, []
            return None, ["Расчёт ещё выполняется. Повторите запрос через несколько секунд."]

        return payload, []

    @staticmethod
    def _can_use_early_snapshot(
        payload: ScenarioEffectsCachePayload,
        request: ScenarioAbsoluteRequestDTO,
    ) -> bool:
        snapshot = payload.early_group_snapshot
        if snapshot is None:
            return False
        if request.group_by != "cargo_group" or request.group_by_inner != "none":
            return False
        return snapshot.group_dim == "cargo_group"

    @staticmethod
    def _year_values_from_early_snapshot(
        snapshot: EarlyGroupSnapshot | None,
        *,
        years: list[int],
        metric: str,
    ) -> dict[tuple[str, ...], dict[int, Decimal]]:
        if snapshot is None:
            return {}

        source = (
            snapshot.charge_by_year if metric == "charge" else snapshot.volume_by_year
        )
        year_values: dict[tuple[str, ...], dict[int, Decimal]] = {}
        for label_index, label in enumerate(snapshot.dimension_labels):
            values: dict[int, Decimal] = {}
            for year in years:
                year_bucket = source.get(year) or []
                if label_index < len(year_bucket):
                    values[year] = year_bucket[label_index]
                else:
                    values[year] = Decimal("0")
            year_values[(label,)] = values
        return year_values

    def _aggregate_volumes_from_compact(
        self,
        payload: ScenarioEffectsCachePayload,
        request: ScenarioAbsoluteRequestDTO,
    ) -> dict[tuple[str, ...], dict[int, Decimal]]:
        assert payload.compact is not None
        compact = payload.compact
        if compact.volume_by_year is not None:
            return aggregate_compact_year_values(
                compact,
                group_by=request.group_by,
                group_by_inner=request.group_by_inner,
                cargo_groups=[],
                holdings=[],
                values_by_year=compact.volume_by_year,
            )

        volume_buckets = aggregate_compact_value(
            compact,
            values=compact.volume_tons,
            group_by=request.group_by,
            group_by_inner=request.group_by_inner,
            cargo_groups=[],
            holdings=[],
        )
        return {
            key: {year: volume for year in payload.years}
            for key, volume in volume_buckets.items()
        }

    @staticmethod
    def _year_values_are_empty(
        year_values: dict[tuple[str, ...], dict[int, Decimal]],
    ) -> bool:
        if not year_values:
            return True
        return all(
            value == 0
            for values in year_values.values()
            for value in values.values()
        )

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
        group_by: str,
        group_by_inner: str,
        format_value,
        fallout_year_values: dict[tuple[str, ...], dict[int, Decimal]] | None = None,
        format_fallout=None,
    ) -> list[AbsoluteTableRowDTO]:
        rows: list[AbsoluteTableRowDTO] = []

        grand_years: dict[int, Decimal] = {year: Decimal("0") for year in years}
        grand_fallout: dict[int, Decimal] = {year: Decimal("0") for year in years}
        for key, values in year_values.items():
            if group_by_inner != "none":
                if len(key) != 2 or key[1] != "ИТОГО":
                    continue
            elif len(key) != 1:
                continue
            for year in years:
                gross = values.get(year, Decimal("0"))
                fallout = Decimal("0")
                if fallout_year_values is not None:
                    fallout = fallout_year_values.get(key, {}).get(year, Decimal("0"))
                grand_years[year] += gross + fallout
                grand_fallout[year] += fallout

        rows.append(
            _row_from_values(
                "ИТОГО",
                grand_years,
                years=years,
                format_value=format_value,
                is_subtotal=True,
                fallout_values=grand_fallout if fallout_year_values is not None else None,
                format_fallout=format_fallout,
            ),
        )

        if group_by_inner == "none":
            keys = list(key for key in year_values if len(key) == 1)
            if group_by == "cargo_group":
                keys.sort(key=lambda k: cargo_group_sort_key(k[0]))
            else:
                keys.sort(
                    key=lambda k: sum(year_values[k].values(), Decimal("0")),
                    reverse=True,
                )
            for key in keys:
                rows.append(
                    _row_from_values(
                        key[0],
                        _net_year_values(
                            year_values.get(key, {}),
                            fallout_year_values.get(key, {}) if fallout_year_values else None,
                            years=years,
                        ),
                        years=years,
                        format_value=format_value,
                        is_subtotal=False,
                        fallout_values=(
                            fallout_year_values.get(key) if fallout_year_values else None
                        ),
                        format_fallout=format_fallout,
                    ),
                )
            return rows

        outers = sort_group_labels(
            {key[0] for key in year_values if len(key) == 2},
            dimension=group_by,
        )
        for outer in outers:
            subtotal_key = (outer, "ИТОГО")
            if subtotal_key in year_values:
                rows.append(
                    _row_from_values(
                        outer,
                        _net_year_values(
                            year_values.get(subtotal_key, {}),
                            (
                                fallout_year_values.get(subtotal_key)
                                if fallout_year_values
                                else None
                            ),
                            years=years,
                        ),
                        years=years,
                        format_value=format_value,
                        is_subtotal=True,
                        fallout_values=(
                            fallout_year_values.get(subtotal_key)
                            if fallout_year_values
                            else None
                        ),
                        format_fallout=format_fallout,
                    ),
                )

            inner_keys = [
                key
                for key in year_values
                if len(key) == 2 and key[0] == outer and key[1] != "ИТОГО"
            ]
            if group_by_inner == "cargo_group":
                inner_keys.sort(key=lambda k: cargo_group_sort_key(k[1]))
            else:
                inner_keys.sort(
                    key=lambda k: sum(year_values[k].values(), Decimal("0")),
                    reverse=True,
                )
            for key in inner_keys:
                rows.append(
                    _row_from_values(
                        f"  {key[1]}",
                        _net_year_values(
                            year_values.get(key, {}),
                            fallout_year_values.get(key) if fallout_year_values else None,
                            years=years,
                        ),
                        years=years,
                        format_value=format_value,
                        is_subtotal=False,
                        fallout_values=(
                            fallout_year_values.get(key) if fallout_year_values else None
                        ),
                        format_fallout=format_fallout,
                    ),
                )

        return rows


def _net_year_values(
    gross_values: dict[int, Decimal],
    fallout_values: dict[int, Decimal] | None,
    *,
    years: list[int],
) -> dict[int, Decimal]:
    if fallout_values is None:
        return gross_values
    return {
        year: gross_values.get(year, Decimal("0"))
        + fallout_values.get(year, Decimal("0"))
        for year in years
    }


def _row_from_values(
    label: str,
    values: dict[int, Decimal],
    *,
    years: list[int],
    format_value,
    is_subtotal: bool,
    fallout_values: dict[int, Decimal] | None = None,
    format_fallout=None,
) -> AbsoluteTableRowDTO:
    year_str: dict[str, str] = {}
    years_fallout: dict[str, str] | None = {} if fallout_values is not None else None

    for year in years:
        net = values.get(year, Decimal("0"))
        year_str[str(year)] = format_value(net)
        if fallout_values is not None and format_fallout is not None:
            display = _fallout_display_magnitude(
                fallout_values.get(year, Decimal("0")),
                format_fallout,
            )
            if display is not None:
                years_fallout[str(year)] = display

    total = sum((values.get(year, Decimal("0")) for year in years), Decimal("0"))
    total_fallout_display = None
    if fallout_values is not None and format_fallout is not None:
        total_fallout = sum(
            (fallout_values.get(year, Decimal("0")) for year in years),
            Decimal("0"),
        )
        total_fallout_display = _fallout_display_magnitude(total_fallout, format_fallout)

    if years_fallout is not None and not years_fallout:
        years_fallout = None

    return AbsoluteTableRowDTO(
        label=label,
        is_subtotal=is_subtotal,
        years=year_str,
        total=format_value(total),
        years_fallout=years_fallout,
        total_fallout=total_fallout_display,
    )


def _fallout_display_magnitude(
    fallout: Decimal,
    format_value,
) -> str | None:
    if fallout == 0:
        return None
    sign = "+" if fallout > 0 else "-"
    return f"{sign}{format_value(abs(fallout))}"


def _format_bln(value: Decimal) -> str:
    bln = (value / RUB_PER_BLN).quantize(_BLN_QUANT, rounding=ROUND_HALF_UP)
    return format(bln, "f")


def _format_volume(value: Decimal) -> str:
    mln = (value / TONS_PER_MLN).quantize(_VOLUME_QUANT, rounding=ROUND_HALF_UP)
    return format(mln, "f")


def _total_label(years: list[int]) -> str:
    if not years:
        return "Итого"
    return f"{years[0]}-{years[-1]}"
