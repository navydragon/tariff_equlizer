"""Сдвиг коэффициентов отдельных тарифных решений между годами."""
from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from django.db import transaction

from scenarios.models import Scenario, TariffRule, TariffRuleYearValue

ONE = Decimal("1")


@dataclass(frozen=True)
class ShiftTariffRuleYearsResult:
    scenario_id: int
    from_year: int
    to_year: int
    rules_total: int
    moved: int
    source_reset_to_one: int
    dry_run: bool


def shift_tariff_rule_year_coefficients(
    *,
    scenario: Scenario,
    from_year: int,
    to_year: int,
    dry_run: bool = False,
) -> ShiftTariffRuleYearsResult:
    """
    Для всех отдельных тарифных решений сценария:
    - коэффициент from_year копируется в to_year (если строка from_year есть);
    - коэффициент from_year становится 1 (создаётся при отсутствии).
    """
    if from_year == to_year:
        raise ValueError("Годы «откуда» и «куда» должны отличаться")

    rules = list(
        TariffRule.objects.filter(scenario_id=scenario.id).only("id").order_by("id")
    )
    rule_ids = [rule.id for rule in rules]
    if not rule_ids:
        return ShiftTariffRuleYearsResult(
            scenario_id=scenario.id,
            from_year=from_year,
            to_year=to_year,
            rules_total=0,
            moved=0,
            source_reset_to_one=0,
            dry_run=dry_run,
        )

    year_rows = TariffRuleYearValue.objects.filter(
        tariff_rule_id__in=rule_ids,
        year__in=(from_year, to_year),
    )
    by_rule_year: dict[tuple[int, int], TariffRuleYearValue] = {
        (row.tariff_rule_id, row.year): row for row in year_rows
    }

    to_create: list[TariffRuleYearValue] = []
    to_update: list[TariffRuleYearValue] = []
    moved = 0
    source_reset_to_one = 0

    for rule_id in rule_ids:
        source = by_rule_year.get((rule_id, from_year))
        target = by_rule_year.get((rule_id, to_year))

        if source is not None:
            moved += 1
            if target is None:
                to_create.append(
                    TariffRuleYearValue(
                        tariff_rule_id=rule_id,
                        year=to_year,
                        coefficient=source.coefficient,
                    )
                )
            elif target.coefficient != source.coefficient:
                target.coefficient = source.coefficient
                to_update.append(target)

            if source.coefficient != ONE:
                source.coefficient = ONE
                to_update.append(source)
            source_reset_to_one += 1
        else:
            to_create.append(
                TariffRuleYearValue(
                    tariff_rule_id=rule_id,
                    year=from_year,
                    coefficient=ONE,
                )
            )
            source_reset_to_one += 1

    if dry_run:
        return ShiftTariffRuleYearsResult(
            scenario_id=scenario.id,
            from_year=from_year,
            to_year=to_year,
            rules_total=len(rule_ids),
            moved=moved,
            source_reset_to_one=source_reset_to_one,
            dry_run=True,
        )

    with transaction.atomic():
        if to_create:
            TariffRuleYearValue.objects.bulk_create(to_create)
        if to_update:
            TariffRuleYearValue.objects.bulk_update(to_update, ["coefficient"])

    return ShiftTariffRuleYearsResult(
        scenario_id=scenario.id,
        from_year=from_year,
        to_year=to_year,
        rules_total=len(rule_ids),
        moved=moved,
        source_reset_to_one=source_reset_to_one,
        dry_run=False,
    )
