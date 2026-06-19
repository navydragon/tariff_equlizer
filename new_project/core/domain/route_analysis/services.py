from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from calculations.domain.services.tariff_load import TariffLoadService
from core.models import Route
from scenarios.domain.services.price_change import PriceChangeSettingService
from scenarios.domain.utils.elasticity_matching import (
    compute_retention_coefficient,
    marginality_ratio_from_percent,
)
from scenarios.domain.utils.fx_rates import load_fx_rates_by_year, missing_fx_years
from scenarios.domain.utils.price_inflation import (
    index_money_series,
    load_inflation_rates_by_year,
)
from scenarios.models import Scenario, ScenarioPriceChangeSetting

from calculations.domain.dto.tariff_load import RouteTariffLoadDTO

from .dto import (
    RouteAnalysisRequestDTO,
    RouteAnalysisResponseDTO,
    RouteAnalysisTableRowDTO,
    EffectRowDTO,
    EffectsResponseDTO,
    EffectYearValueDTO,
    EqualizerResponseDTO,
    EqualizerTypeDTO,
    KpiMetricDTO,
    KpiResponseDTO,
    KpiYearDTO,
    TransportStructureDTO,
)
from .rzd_tariff_sensitivity import build_rzd_tariff_sensitivity


def _to_decimal_or_zero(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.01"))


def _quantize_coefficient(value: Decimal) -> Decimal:
    return value.quantize(Decimal("0.0001"))


def _retention_volume_delta_mln_tons(
    route: Route,
    retention_coefficient: Decimal | None,
) -> Decimal | None:
    if retention_coefficient is None:
        return None
    base_volume = route.transport_volume_tons
    if base_volume is None or base_volume <= 0:
        return None
    return _quantize_money(
        base_volume * (retention_coefficient - Decimal("1")) / Decimal("1000000"),
    )


def _is_internal_route(route: Route) -> bool:
    if not route.message_type_id:
        return False
    name = (route.message_type.name or "").lower()
    return "внутр" in name


def _is_export_route(route: Route) -> bool:
    if not route.message_type_id:
        return False
    name = (route.message_type.name or "").lower()
    return "экспорт" in name


def _route_cost_baseline(route: Route) -> Decimal:
    production_cost = route.production_cost_per_ton
    total_cost = route.total_cost_per_ton
    return _to_decimal_or_zero(
        production_cost if production_cost is not None else total_cost,
    )


class RouteAnalysisService:
    def __init__(self):
        self.tariff_load_service = TariffLoadService()
        self.price_change_service = PriceChangeSettingService()

    def calculate(
        self,
        *,
        request_dto: RouteAnalysisRequestDTO,
        scenario: Scenario,
        route: Route,
    ) -> RouteAnalysisResponseDTO:
        years = list(
            range(int(scenario.start_year), int(scenario.end_year) + 1),
        )
        overrides = request_dto.overrides or {}

        base_overrides = overrides.get("base")
        rules_overrides = overrides.get("rules")

        tariff_load = self.tariff_load_service.calculate_route(
            scenario=scenario,
            route=route,
            base_coef_overrides=base_overrides,
            rules_coef_overrides=rules_overrides,
        )

        price_change_settings = self.price_change_service.get_settings(scenario.id)
        inflation_rates = load_inflation_rates_by_year(scenario)

        cost_scalar = _route_cost_baseline(route)
        oper_scalar = _to_decimal_or_zero(route.operators_cost_per_ton)
        per_scalar = _to_decimal_or_zero(route.transshipment_cost_per_ton)
        price_scalar = _to_decimal_or_zero(route.market_price_per_ton)

        cost_values = self._money_series_for_parameter(
            years=years,
            scalar=cost_scalar,
            analysis_key="cost",
            price_change_key=ScenarioPriceChangeSetting.Parameter.COST,
            overrides=overrides.get("cost"),
            price_change_settings=price_change_settings,
            inflation_rates=inflation_rates,
        )
        oper_values = self._money_series_for_parameter(
            years=years,
            scalar=oper_scalar,
            analysis_key="oper",
            price_change_key=ScenarioPriceChangeSetting.Parameter.OPERATORS,
            overrides=overrides.get("oper"),
            price_change_settings=price_change_settings,
            inflation_rates=inflation_rates,
        )
        per_values = self._money_series_for_parameter(
            years=years,
            scalar=per_scalar,
            analysis_key="per",
            price_change_key=ScenarioPriceChangeSetting.Parameter.TRANSSHIPMENT,
            overrides=overrides.get("per"),
            price_change_settings=price_change_settings,
            inflation_rates=inflation_rates,
        )
        price_values = self._build_market_price_series(
            years=years,
            route=route,
            scenario=scenario,
            scalar=price_scalar,
            overrides=overrides,
            price_change_settings=price_change_settings,
            inflation_rates=inflation_rates,
        )

        rzd_values = [
            tariff_load.rzd_by_year.get(year, Decimal("0")) for year in years
        ]
        transport_values = [
            _quantize_money(
                rzd_values[index] + oper_values[index] + per_values[index],
            )
            for index in range(len(years))
        ]

        marginality_values: list[dict[str, str]] = []
        for index in range(len(years)):
            rzd = rzd_values[index]
            price = price_values[index]
            marginality_rub = (
                price - cost_values[index] - rzd - oper_values[index] - per_values[index]
            )
            marginality_pct = (
                (marginality_rub * Decimal("100") / price)
                if price > 0
                else Decimal("0")
            )
            marginality_values.append(
                {
                    "rub": _format_decimal(_quantize_money(marginality_rub)),
                    "pct": _format_decimal(marginality_pct),
                },
            )

        def money_row(
            key: str,
            label: str,
            values: list[Decimal],
        ) -> RouteAnalysisTableRowDTO:
            return RouteAnalysisTableRowDTO(
                key=key,
                label=label,
                values=[_format_decimal(value) for value in values],
                format="money",
            )

        rows: list[RouteAnalysisTableRowDTO] = [
            money_row("price_rub", "Цена, руб.", price_values),
            money_row("cost", "Себестоимость, руб.", cost_values),
            money_row("transport", "Транспортные затраты, руб.", transport_values),
            money_row("rzd", "Ж/Д тариф, руб.", rzd_values),
            money_row("operators", "Вагонная составляющая, руб.", oper_values),
            money_row("transshipment", "Перевалка, руб.", per_values),
            RouteAnalysisTableRowDTO(
                key="marginality",
                label="Маржинальная прибыль, руб. (%)",
                values=marginality_values,
                format="marginality",
            ),
        ]

        fx_rates = load_fx_rates_by_year(scenario)
        equalizer = self._build_equalizer(
            years=years,
            route=route,
            scenario=scenario,
            tariff_load=tariff_load,
            cost_values=cost_values,
            oper_values=oper_values,
            per_values=per_values,
            price_values=price_values,
            fx_rates=fx_rates,
        )

        transport_structure = self._build_transport_structure(
            years=years,
            route=route,
            tariff_load=tariff_load,
            price_values=price_values,
            transport_values=transport_values,
            marginality_values=marginality_values,
        )
        effects = self._build_effects(years=years, tariff_load=tariff_load)
        kpi = self._build_kpi(
            years=years,
            scenario=scenario,
            route=route,
            price_values=price_values,
            transport_values=transport_values,
            rzd_values=rzd_values,
            marginality_values=marginality_values,
        )
        rzd_tariff_sensitivity = build_rzd_tariff_sensitivity(
            route=route,
            scenario=scenario,
        )

        return RouteAnalysisResponseDTO(
            scenario_id=request_dto.scenario_id,
            route_id=request_dto.route_id,
            route_code=route.route_code or "",
            years=years,
            rows=rows,
            equalizer=equalizer,
            transport_structure=transport_structure,
            effects=effects,
            kpi=kpi,
            rzd_tariff_sensitivity=rzd_tariff_sensitivity,
        )

    @staticmethod
    def _series_for_years(
        *,
        years: list[int],
        scalar: Decimal,
        overrides: dict[int, Decimal] | None,
    ) -> list[Decimal]:
        return [
            overrides.get(year, scalar) if overrides else scalar for year in years
        ]

    def _money_series_for_parameter(
        self,
        *,
        years: list[int],
        scalar: Decimal,
        analysis_key: str,
        price_change_key: str,
        overrides: dict[int, Decimal] | None,
        price_change_settings: dict[str, str],
        inflation_rates: dict[int, Decimal] | None,
    ) -> list[Decimal]:
        if overrides:
            return self._series_for_years(
                years=years,
                scalar=scalar,
                overrides=overrides,
            )

        mode = price_change_settings.get(price_change_key)
        if (
            mode == ScenarioPriceChangeSetting.Mode.INFLATION
            and inflation_rates is not None
        ):
            indexed = index_money_series(years, scalar, inflation_rates)
            return [indexed[year] for year in years]

        return self._series_for_years(years=years, scalar=scalar, overrides=None)

    def _build_market_price_series(
        self,
        *,
        years: list[int],
        route: Route,
        scenario: Scenario,
        scalar: Decimal,
        overrides: dict[str, dict[int, Decimal]] | None,
        price_change_settings: dict[str, str],
        inflation_rates: dict[int, Decimal] | None,
    ) -> list[Decimal]:
        overrides = overrides or {}
        price_rub_overrides = overrides.get("price_rub")

        base_series = self._money_series_for_parameter(
            years=years,
            scalar=scalar,
            analysis_key="price_rub",
            price_change_key=ScenarioPriceChangeSetting.Parameter.MARKET_PRICE,
            overrides=price_rub_overrides,
            price_change_settings=price_change_settings,
            inflation_rates=inflation_rates,
        )

        use_fx = (
            _is_export_route(route)
            and scenario.export_price_mode == Scenario.ExportPriceMode.BY_FX
        )
        if not use_fx:
            return base_series

        fx_rates = load_fx_rates_by_year(scenario)
        if not fx_rates:
            return base_series

        fx_overrides = overrides.get("fx")
        fx_series = self._fx_series_for_years(
            years=years,
            fx_rates=fx_rates,
            overrides=fx_overrides,
        )
        if not fx_series or fx_series[0] <= 0:
            return base_series

        usd_y0 = scalar / fx_series[0]
        market_mode = price_change_settings.get(
            ScenarioPriceChangeSetting.Parameter.MARKET_PRICE,
        )
        if (
            market_mode == ScenarioPriceChangeSetting.Mode.INFLATION
            and inflation_rates is not None
        ):
            usd_by_year = index_money_series(years, usd_y0, inflation_rates)
            usd_values = [usd_by_year[year] for year in years]
        else:
            usd_values = [usd_y0 for _ in years]

        rub_series = [
            _quantize_money(usd_values[index] * fx_series[index])
            for index in range(len(years))
        ]

        if price_rub_overrides:
            return self._series_for_years(
                years=years,
                scalar=scalar,
                overrides=price_rub_overrides,
            )
        return rub_series

    @staticmethod
    def _fx_series_for_years(
        *,
        years: list[int],
        fx_rates: dict[int, Decimal],
        overrides: dict[int, Decimal] | None,
    ) -> list[Decimal]:
        result: list[Decimal] = []
        for year in years:
            if overrides and year in overrides:
                result.append(overrides[year])
            else:
                result.append(fx_rates.get(year, Decimal("0")))
        return result

    def _build_equalizer(
        self,
        *,
        years: list[int],
        route: Route,
        scenario: Scenario,
        tariff_load: Any,
        cost_values: list[Decimal],
        oper_values: list[Decimal],
        per_values: list[Decimal],
        price_values: list[Decimal],
        fx_rates: dict[int, Decimal] | None,
    ) -> EqualizerResponseDTO:
        is_internal = _is_internal_route(route)
        is_export = _is_export_route(route)

        def coef_values(coef_map: dict[int, Decimal]) -> dict[str, str]:
            return {
                str(year): _format_decimal(coef_map.get(year, Decimal("1")))
                for year in years
            }

        def money_values_from_series(values: list[Decimal]) -> dict[str, str]:
            return {
                str(year): _format_decimal(values[index])
                for index, year in enumerate(years)
            }

        types = [
            EqualizerTypeDTO(
                key="cost",
                label="Себестоимость",
                unit="руб./т",
                step="1",
                values=money_values_from_series(cost_values),
                visible=True,
            ),
            EqualizerTypeDTO(
                key="oper",
                label="Операторы",
                unit="руб./т",
                step="1",
                values=money_values_from_series(oper_values),
                visible=True,
            ),
            EqualizerTypeDTO(
                key="per",
                label="Перевалка",
                unit="руб./т",
                step="1",
                values=money_values_from_series(per_values),
                visible=not is_internal,
            ),
            EqualizerTypeDTO(
                key="price_rub",
                label="Цена (руб.)",
                unit="руб./т",
                step="1",
                values=money_values_from_series(price_values),
                visible=True,
            ),
            EqualizerTypeDTO(
                key="base",
                label="Индексация",
                unit="индекс",
                step="0.01",
                values=coef_values(tariff_load.base_coefficient_by_year),
                visible=True,
            ),
            EqualizerTypeDTO(
                key="rules",
                label="Тарифные решения",
                unit="индекс",
                step="0.001",
                values=coef_values(tariff_load.rules_coefficient_by_year),
                visible=True,
            ),
        ]

        if is_export:
            types.append(self._build_fx_equalizer_type(years=years, fx_rates=fx_rates))

        return EqualizerResponseDTO(types=types)

    def _build_fx_equalizer_type(
        self,
        *,
        years: list[int],
        fx_rates: dict[int, Decimal] | None,
    ) -> EqualizerTypeDTO:
        if fx_rates is None:
            return EqualizerTypeDTO(
                key="fx",
                label="Курс $",
                unit="руб./$",
                step="0.0001",
                values={},
                visible=True,
                editable=False,
                notice=(
                    "К сценарию не прикреплён набор курсов валют. "
                    "Задайте курсы на вкладке «Курсы валют» сценария."
                ),
            )

        missing = missing_fx_years(years, fx_rates)
        if missing:
            years_text = ", ".join(str(y) for y in missing)
            return EqualizerTypeDTO(
                key="fx",
                label="Курс $",
                unit="руб./$",
                step="0.0001",
                values={},
                visible=True,
                editable=False,
                notice=(
                    f"Не задан курс USD/RUB для годов: {years_text}. "
                    "Заполните курсы на вкладке «Курсы валют» сценария."
                ),
            )

        values = {
            str(year): _format_decimal(fx_rates[year])
            for year in years
        }
        return EqualizerTypeDTO(
            key="fx",
            label="Курс $",
            unit="руб./$",
            step="0.0001",
            values=values,
            visible=True,
            editable=True,
            notice="",
        )

    def _build_transport_structure(
        self,
        *,
        years: list[int],
        route: Route,
        tariff_load: RouteTariffLoadDTO,
        price_values: list[Decimal],
        transport_values: list[Decimal],
        marginality_values: list[dict[str, str]],
    ) -> TransportStructureDTO:
        transport_pct: dict[str, str] = {}
        marginality_pct: dict[str, str] = {}

        for index, year in enumerate(years):
            price = price_values[index]
            if price > 0:
                transport_pct[str(year)] = _format_decimal(
                    _quantize_money(transport_values[index] * Decimal("100") / price),
                )
                marginality_pct[str(year)] = marginality_values[index]["pct"]
            else:
                transport_pct[str(year)] = "0"
                marginality_pct[str(year)] = "0"

        empty_initial = route.rzd_cost_empty_per_ton or Decimal("0")
        return TransportStructureDTO(
            show_empty_leg=empty_initial > 0,
            rzd_loaded_by_year={
                str(year): _format_decimal(tariff_load.rzd_loaded_by_year.get(year, Decimal("0")))
                for year in years
            },
            rzd_empty_by_year={
                str(year): _format_decimal(tariff_load.rzd_empty_by_year.get(year, Decimal("0")))
                for year in years
            },
            transport_pct_by_year=transport_pct,
            marginality_pct_by_year=marginality_pct,
        )

    def _build_effects(
        self,
        *,
        years: list[int],
        tariff_load: RouteTariffLoadDTO,
    ) -> EffectsResponseDTO:
        rows: list[EffectRowDTO] = []

        def effect_row(
            key: str,
            label: str,
            load_map: dict[int, Decimal],
        ) -> EffectRowDTO:
            values_by_year: dict[str, EffectYearValueDTO] = {}
            for index, year in enumerate(years):
                rub = load_map.get(year, Decimal("0"))
                if index == 0:
                    values_by_year[str(year)] = EffectYearValueDTO(
                        rub=_format_decimal(rub),
                        pct="0",
                    )
                    continue
                prev_year = years[index - 1]
                prev_rzd = tariff_load.rzd_by_year.get(prev_year, Decimal("0"))
                pct = (
                    _format_decimal(rub * Decimal("100") / prev_rzd)
                    if prev_rzd > 0
                    else "0"
                )
                values_by_year[str(year)] = EffectYearValueDTO(
                    rub=_format_decimal(rub),
                    pct=pct,
                )
            return EffectRowDTO(key=key, label=label, values_by_year=values_by_year)

        rows.append(
            effect_row(
                "total",
                "Совокупная тарифная нагрузка",
                tariff_load.tariff_load.total,
            ),
        )
        rows.append(
            effect_row(
                "base",
                "Базовая индексация с надбавками",
                tariff_load.tariff_load.base,
            ),
        )
        rows.append(
            effect_row(
                "rules",
                "Тарифные решения, в т.ч.",
                tariff_load.tariff_load.rules,
            ),
        )

        for rule_effect in tariff_load.rule_effects:
            rows.append(
                effect_row(
                    f"rule_{rule_effect.rule_id}",
                    rule_effect.name,
                    rule_effect.load_by_year,
                ),
            )

        return EffectsResponseDTO(rows=rows)

    def _build_kpi(
        self,
        *,
        years: list[int],
        scenario: Scenario,
        route: Route,
        price_values: list[Decimal],
        transport_values: list[Decimal],
        rzd_values: list[Decimal],
        marginality_values: list[dict[str, str]],
    ) -> KpiResponseDTO:
        by_year: list[KpiYearDTO] = []

        for index, year in enumerate(years):
            if index == 0:
                continue

            price = price_values[index]
            transport_rub = transport_values[index]
            rzd_rub = rzd_values[index]
            margin_rub = marginality_values[index]["rub"]
            margin_pct = marginality_values[index]["pct"]
            retention_coefficient = compute_retention_coefficient(
                route,
                scenario,
                marginality_ratio_from_percent(Decimal(margin_pct)),
            )
            retention_pct = (
                _format_decimal(_quantize_coefficient(retention_coefficient))
                if retention_coefficient is not None
                else None
            )
            loading_mln_tons = _retention_volume_delta_mln_tons(
                route,
                retention_coefficient,
            )
            retention_delta = (
                _format_decimal(loading_mln_tons)
                if loading_mln_tons is not None
                else None
            )

            def metric(label: str, rub: Decimal, pct_of_price: Decimal) -> KpiMetricDTO:
                return KpiMetricDTO(
                    label=label,
                    rub=_format_decimal(_quantize_money(rub)),
                    pct=_format_decimal(pct_of_price) if price > 0 else "0",
                )

            transport_pct = (
                transport_rub * Decimal("100") / price if price > 0 else Decimal("0")
            )
            rzd_pct = rzd_rub * Decimal("100") / price if price > 0 else Decimal("0")

            by_year.append(
                KpiYearDTO(
                    year=year,
                    transport=metric(
                        "Транспортная составляющая",
                        transport_rub,
                        transport_pct,
                    ),
                    rzd=metric(
                        'Расходы на оплату услуг ОАО "РЖД"',
                        rzd_rub,
                        rzd_pct,
                    ),
                    marginality=KpiMetricDTO(
                        label="Маржинальность грузоотправителя",
                        rub=margin_rub,
                        pct=margin_pct,
                    ),
                    volume_share=KpiMetricDTO(
                        label="Доля в объеме перевозок",
                        rub=None,
                        pct=None,
                    ),
                    elasticity=KpiMetricDTO(
                        label="Коэффициент сохранения грузовой базы",
                        rub=retention_delta,
                        pct=retention_pct,
                    ),
                ),
            )

        return KpiResponseDTO(by_year=by_year)
