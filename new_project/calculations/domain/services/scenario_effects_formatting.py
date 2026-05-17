from __future__ import annotations

from collections import defaultdict
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP

from calculations.domain.dto.scenario_effects import EffectKpiCardDTO

_BLN_DIVISOR = Decimal("1000000")
_PCT_QUANT = Decimal("0.1")
_THS_QUANT = Decimal("0.01")


@dataclass
class GlobalTotals:
    baseline_total: Decimal = Decimal("0")
    base_by_year: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    rules_by_year: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))
    charge_by_year: dict[int, Decimal] = field(default_factory=lambda: defaultdict(Decimal))


def format_ths(value: Decimal) -> str:
    return format(value.quantize(_THS_QUANT, rounding=ROUND_HALF_UP), "f")


def format_bln(value: Decimal) -> str:
    bln = (value / _BLN_DIVISOR).quantize(Decimal("0.1"), rounding=ROUND_HALF_UP)
    return format(bln, "f")


def pct(part: Decimal, whole: Decimal) -> str:
    if whole <= 0:
        return "0.0"
    value = (part * Decimal("100") / whole).quantize(
        _PCT_QUANT,
        rounding=ROUND_HALF_UP,
    )
    return format(value, "f")


def build_cards_from_totals(
    totals: GlobalTotals,
    years: list[int],
) -> list[EffectKpiCardDTO]:
    cards: list[EffectKpiCardDTO] = []

    for index, year in enumerate(years):
        if index == 0:
            continue

        base_sum = totals.base_by_year[year]
        rules_sum = totals.rules_by_year[year]
        total_sum = base_sum + rules_sum

        prev_year = years[index - 1]
        if index == 1:
            prev_denominator = totals.baseline_total
        else:
            prev_denominator = totals.charge_by_year[prev_year]

        cards.append(
            EffectKpiCardDTO(
                year=year,
                total_bln=format_bln(total_sum),
                total_pct=pct(total_sum, prev_denominator),
                base_bln=format_bln(base_sum),
                base_pct=pct(base_sum, prev_denominator),
                rules_bln=format_bln(rules_sum),
                rules_pct=pct(rules_sum, prev_denominator),
            ),
        )

    return cards
