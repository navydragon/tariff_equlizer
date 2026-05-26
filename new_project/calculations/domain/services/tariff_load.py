from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from typing import Iterable

from django.db.models import Prefetch

from core.models import Route
from calculations.domain.dto.tariff_load import (
    RouteTariffLoadDTO,
    TariffLoadByYearDTO,
    TariffRuleEffectDTO,
)
from scenarios.domain.repositories import (
    BTDCategoryRepository,
    BTDCategoryValueRepository,
)
from scenarios.domain.services.btd_coefficients import (
    compute_total_coefficient_decimals_by_year,
)
from scenarios.domain.utils.tariff_conditions import route_matches_tariff_conditions
from scenarios.models import Scenario, TariffRule, TariffRuleCondition, TariffRuleYearValue

_MONEY_QUANT = Decimal("0.01")


def _quantize_money(value: Decimal) -> Decimal:
    return value.quantize(_MONEY_QUANT)


def _effective_rule_coefficient(
    coefficient: Decimal,
    base_percent: Decimal,
) -> Decimal:
    return Decimal("1") + (coefficient - Decimal("1")) * base_percent / Decimal("100")


def _index_rzd_chain(
    *,
    years: list[int],
    initial_value: Decimal,
    base_coef_by_year: dict[int, Decimal],
    rules_coef_by_year: dict[int, Decimal],
) -> dict[int, Decimal]:
    result: dict[int, Decimal] = {}
    prev_rzd = _quantize_money(initial_value)

    for index, year in enumerate(years):
        if index == 0:
            result[year] = prev_rzd
            continue

        base_coef = base_coef_by_year.get(year, Decimal("1"))
        rules_coef = rules_coef_by_year.get(year, Decimal("1"))
        current_rzd = prev_rzd * (base_coef + rules_coef - Decimal("1"))

        try:
            current_rzd = _quantize_money(current_rzd)
        except InvalidOperation:
            current_rzd = prev_rzd

        result[year] = current_rzd
        prev_rzd = current_rzd

    return result


@dataclass(frozen=True)
class ScenarioTariffContext:
    years: list[int]
    base_coef_by_year: dict[int, Decimal]
    rules: list[TariffRule]


@dataclass(frozen=True)
class FreightChargeEffects:
    charge_by_year: dict[int, Decimal]
    base_by_year: dict[int, Decimal]
    rules_by_year: dict[int, Decimal]
    total_by_year: dict[int, Decimal]
    rule_by_year: dict[int, dict[int, Decimal]]


class TariffLoadService:
    def __init__(self):
        self.category_repository = BTDCategoryRepository()
        self.value_repository = BTDCategoryValueRepository()

    def _load_base_coefficients(self, scenario: Scenario) -> dict[int, Decimal]:
        years = list(range(scenario.start_year, scenario.end_year + 1))
        categories = list(self.category_repository.list_by_scenario(scenario.id))
        values = list(self.value_repository.list_by_scenario(scenario.id))
        value_map: dict[tuple[int, int], str] = {
            (value.category_id, value.year): str(value.value) for value in values
        }
        return compute_total_coefficient_decimals_by_year(
            years, categories, value_map
        )

    def _load_tariff_rules(self, scenario_id: int) -> list[TariffRule]:
        return list(
            TariffRule.objects.filter(scenario_id=scenario_id)
            .prefetch_related(
                Prefetch(
                    "conditions",
                    queryset=TariffRuleCondition.objects.order_by("position", "id"),
                ),
                Prefetch(
                    "year_values",
                    queryset=TariffRuleYearValue.objects.order_by("year"),
                ),
            )
            .order_by("position", "id")
        )

    @staticmethod
    def _rule_conditions_payload(rule: TariffRule) -> list[dict]:
        return [
            {
                "parameter": condition.parameter,
                "operator": condition.operator,
                "values": condition.values,
            }
            for condition in rule.conditions.all()
        ]

    @staticmethod
    def _rule_year_coefficients(rule: TariffRule) -> dict[int, Decimal]:
        return {value.year: value.coefficient for value in rule.year_values.all()}

    def _rules_coefficient_for_year(
        self,
        *,
        route: Route,
        year: int,
        rules: list[TariffRule],
    ) -> Decimal:
        combined = Decimal("1")
        for rule in rules:
            if not route_matches_tariff_conditions(
                route, self._rule_conditions_payload(rule)
            ):
                continue
            raw_coef = self._rule_year_coefficients(rule).get(year, Decimal("1"))
            combined *= _effective_rule_coefficient(raw_coef, rule.base_percent)
        return combined

    def _build_rule_effects(
        self,
        *,
        route: Route,
        years: list[int],
        rules: list[TariffRule],
        rzd_by_year: dict[int, Decimal],
    ) -> list[TariffRuleEffectDTO]:
        effects: list[TariffRuleEffectDTO] = []

        for rule in rules:
            if not route_matches_tariff_conditions(
                route, self._rule_conditions_payload(rule)
            ):
                continue

            load_by_year: dict[int, Decimal] = {}
            year_coefs = self._rule_year_coefficients(rule)

            for index, year in enumerate(years):
                if index == 0:
                    load_by_year[year] = Decimal("0")
                    continue

                prev_year = years[index - 1]
                prev_rzd = rzd_by_year.get(prev_year, Decimal("0"))
                raw_coef = year_coefs.get(year, Decimal("1"))
                eff_coef = _effective_rule_coefficient(raw_coef, rule.base_percent)
                load_by_year[year] = _quantize_money(
                    prev_rzd * (eff_coef - Decimal("1")),
                )

            if sum(load_by_year.values(), Decimal("0")) <= 0:
                continue

            effects.append(
                TariffRuleEffectDTO(
                    rule_id=rule.id,
                    name=rule.name,
                    load_by_year=load_by_year,
                ),
            )

        return effects

    def calculate_route(
        self,
        *,
        scenario: Scenario,
        route: Route,
        base_coef_overrides: dict[int, Decimal] | None = None,
        rules_coef_overrides: dict[int, Decimal] | None = None,
    ) -> RouteTariffLoadDTO:
        years = list(range(scenario.start_year, scenario.end_year + 1))
        base_coef_by_year = self._load_base_coefficients(scenario)
        if base_coef_overrides:
            base_coef_by_year = {
                **base_coef_by_year,
                **base_coef_overrides,
            }
        rules = self._load_tariff_rules(scenario.id)

        rules_coef_by_year = {
            year: self._rules_coefficient_for_year(route=route, year=year, rules=rules)
            for year in years
        }
        if rules_coef_overrides:
            rules_coef_by_year = {
                **rules_coef_by_year,
                **rules_coef_overrides,
            }

        initial_rzd = route.rzd_cost_total_per_ton or Decimal("0")
        initial_loaded = route.rzd_cost_loaded_per_ton or initial_rzd
        initial_empty = route.rzd_cost_empty_per_ton or Decimal("0")

        rzd_by_year = _index_rzd_chain(
            years=years,
            initial_value=initial_rzd,
            base_coef_by_year=base_coef_by_year,
            rules_coef_by_year=rules_coef_by_year,
        )
        rzd_loaded_by_year = _index_rzd_chain(
            years=years,
            initial_value=initial_loaded,
            base_coef_by_year=base_coef_by_year,
            rules_coef_by_year=rules_coef_by_year,
        )
        rzd_empty_by_year = _index_rzd_chain(
            years=years,
            initial_value=initial_empty,
            base_coef_by_year=base_coef_by_year,
            rules_coef_by_year=rules_coef_by_year,
        )

        load_total: dict[int, Decimal] = {}
        load_base: dict[int, Decimal] = {}
        load_rules: dict[int, Decimal] = {}

        for index, year in enumerate(years):
            if index == 0:
                load_total[year] = Decimal("0")
                load_base[year] = Decimal("0")
                load_rules[year] = Decimal("0")
                continue

            prev_year = years[index - 1]
            prev_rzd = rzd_by_year.get(prev_year, Decimal("0"))
            base_coef = base_coef_by_year.get(year, Decimal("1"))
            rules_coef = rules_coef_by_year.get(year, Decimal("1"))

            base_increment = _quantize_money(prev_rzd * (base_coef - Decimal("1")))
            rules_increment = _quantize_money(prev_rzd * (rules_coef - Decimal("1")))

            load_base[year] = base_increment
            load_rules[year] = rules_increment
            load_total[year] = _quantize_money(base_increment + rules_increment)

        rule_effects = self._build_rule_effects(
            route=route,
            years=years,
            rules=rules,
            rzd_by_year=rzd_by_year,
        )

        return RouteTariffLoadDTO(
            route_id=route.id,
            route_code=route.route_code or "",
            years=years,
            rzd_by_year=rzd_by_year,
            rzd_loaded_by_year=rzd_loaded_by_year,
            rzd_empty_by_year=rzd_empty_by_year,
            base_coefficient_by_year=base_coef_by_year,
            rules_coefficient_by_year=rules_coef_by_year,
            tariff_load=TariffLoadByYearDTO(
                total=load_total,
                base=load_base,
                rules=load_rules,
            ),
            rule_effects=rule_effects,
        )

    def calculate_routes(
        self,
        *,
        scenario: Scenario,
        routes: Iterable[Route],
    ) -> list[RouteTariffLoadDTO]:
        return [self.calculate_route(scenario=scenario, route=route) for route in routes]

    def build_scenario_context(self, scenario: Scenario) -> ScenarioTariffContext:
        years = list(range(scenario.start_year, scenario.end_year + 1))
        return ScenarioTariffContext(
            years=years,
            base_coef_by_year=self._load_base_coefficients(scenario),
            rules=self._load_tariff_rules(scenario.id),
        )

    def build_rule_match_sets(
        self,
        routes_qs,
        rules: list[TariffRule],
    ) -> dict[int, set[int]]:
        from scenarios.domain.utils.tariff_conditions import apply_tariff_conditions

        match_sets: dict[int, set[int]] = {}
        for rule in rules:
            conditions = self._rule_conditions_payload(rule)
            match_sets[rule.id] = set(
                apply_tariff_conditions(routes_qs, conditions).values_list(
                    "id",
                    flat=True,
                ),
            )
        return match_sets

    def rules_coef_by_year_for_route(
        self,
        route: Route,
        context: ScenarioTariffContext,
        rule_match_sets: dict[int, set[int]] | None = None,
    ) -> dict[int, Decimal]:
        if rule_match_sets is None:
            return {
                year: self._rules_coefficient_for_year(
                    route=route,
                    year=year,
                    rules=context.rules,
                )
                for year in context.years
            }

        return {
            year: self._rules_coefficient_for_year_matches(
                route_id=route.id,
                year=year,
                rules=context.rules,
                rule_match_sets=rule_match_sets,
            )
            for year in context.years
        }

    def _rules_coefficient_for_year_matches(
        self,
        *,
        route_id: int,
        year: int,
        rules: list[TariffRule],
        rule_match_sets: dict[int, set[int]],
    ) -> Decimal:
        combined = Decimal("1")
        for rule in rules:
            if route_id not in rule_match_sets.get(rule.id, ()):
                continue
            raw_coef = self._rule_year_coefficients(rule).get(year, Decimal("1"))
            combined *= _effective_rule_coefficient(raw_coef, rule.base_percent)
        return combined

    def compute_freight_charge_effects(
        self,
        route: Route,
        context: ScenarioTariffContext,
        rule_match_sets: dict[int, set[int]] | None = None,
    ) -> FreightChargeEffects | None:
        initial = route.freight_charge_rub
        if initial is None or initial <= 0:
            return None

        rules_coef_by_year = self.rules_coef_by_year_for_route(
            route,
            context,
            rule_match_sets=rule_match_sets,
        )
        charge_by_year = _index_rzd_chain(
            years=context.years,
            initial_value=initial,
            base_coef_by_year=context.base_coef_by_year,
            rules_coef_by_year=rules_coef_by_year,
        )

        base_by_year: dict[int, Decimal] = {}
        rules_by_year: dict[int, Decimal] = {}
        total_by_year: dict[int, Decimal] = {}
        rule_by_year: dict[int, dict[int, Decimal]] = {
            rule.id: {year: Decimal("0") for year in context.years}
            for rule in context.rules
        }

        for index, year in enumerate(context.years):
            if index == 0:
                base_by_year[year] = Decimal("0")
                rules_by_year[year] = Decimal("0")
                total_by_year[year] = Decimal("0")
                continue

            prev_year = context.years[index - 1]
            prev_charge = charge_by_year.get(prev_year, Decimal("0"))
            base_coef = context.base_coef_by_year.get(year, Decimal("1"))
            rules_coef = rules_coef_by_year.get(year, Decimal("1"))

            base_inc = _quantize_money(prev_charge * (base_coef - Decimal("1")))
            rules_inc = _quantize_money(prev_charge * (rules_coef - Decimal("1")))

            base_by_year[year] = base_inc
            rules_by_year[year] = rules_inc
            total_by_year[year] = _quantize_money(base_inc + rules_inc)

            for rule in context.rules:
                if rule_match_sets is not None:
                    if route.id not in rule_match_sets.get(rule.id, ()):
                        continue
                elif not route_matches_tariff_conditions(
                    route,
                    self._rule_conditions_payload(rule),
                ):
                    continue

                raw_coef = self._rule_year_coefficients(rule).get(year, Decimal("1"))
                eff_coef = _effective_rule_coefficient(raw_coef, rule.base_percent)
                rule_by_year[rule.id][year] = _quantize_money(
                    prev_charge * (eff_coef - Decimal("1")),
                )

        return FreightChargeEffects(
            charge_by_year=charge_by_year,
            base_by_year=base_by_year,
            rules_by_year=rules_by_year,
            total_by_year=total_by_year,
            rule_by_year=rule_by_year,
        )
