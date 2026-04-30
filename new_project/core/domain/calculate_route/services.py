from __future__ import annotations

from decimal import Decimal
from typing import Any, Optional

from core.models import Route
from scenarios.models import Scenario

from .dto import (
    CalculateRouteRequestDTO,
    CalculateRouteResponseDTO,
    CalculateRouteTableRowDTO,
)


def _to_decimal_or_zero(value: Optional[Decimal]) -> Decimal:
    return value if value is not None else Decimal("0")


def _repeat_for_years(value: Any, years: list[int]) -> list[Any]:
    return [value for _ in years]


class CalculateRouteService:
    def calculate(
        self,
        *,
        request_dto: CalculateRouteRequestDTO,
        scenario: Scenario,
        route: Route,
    ) -> CalculateRouteResponseDTO:
        years = list(
            range(int(scenario.start_year), int(scenario.end_year) + 1),
        )

        price_rub = _to_decimal_or_zero(route.market_price_per_ton)
        production_cost = route.production_cost_per_ton
        total_cost = route.total_cost_per_ton
        cost = _to_decimal_or_zero(
            production_cost if production_cost is not None else total_cost,
        )

        rzd = _to_decimal_or_zero(route.rzd_cost_total_per_ton)
        operators = _to_decimal_or_zero(route.operators_cost_per_ton)
        transshipment = _to_decimal_or_zero(route.transshipment_cost_per_ton)
        transport = rzd + operators + transshipment

        marginality_rub = price_rub - cost - rzd - operators - transshipment
        marginality_pct = (
            (marginality_rub * Decimal("100") / price_rub)
            if price_rub > 0
            else Decimal("0")
        )

        def money_row(
            key: str,
            label: str,
            value: Decimal,
        ) -> CalculateRouteTableRowDTO:
            return CalculateRouteTableRowDTO(
                key=key,
                label=label,
                values=_repeat_for_years(str(value), years),
                format="money",
            )

        rows: list[CalculateRouteTableRowDTO] = [
            money_row("price_rub", "Цена, руб.", price_rub),
            money_row("cost", "Себестоимость, руб.", cost),
            money_row("transport", "Транспортные затраты, руб.", transport),
            money_row("rzd", "Ж/Д тариф, руб.", rzd),
            money_row("operators", "Вагонная составляющая, руб.", operators),
            money_row("transshipment", "Перевалка, руб.", transshipment),
            CalculateRouteTableRowDTO(
                key="marginality",
                label="Маржинальная прибыль, руб. (%)",
                values=_repeat_for_years(
                    {"rub": str(marginality_rub), "pct": str(marginality_pct)},
                    years,
                ),
                format="marginality",
            ),
        ]

        return CalculateRouteResponseDTO(
            scenario_id=request_dto.scenario_id,
            route_id=request_dto.route_id,
            route_code=route.route_code or "",
            years=years,
            rows=rows,
        )
