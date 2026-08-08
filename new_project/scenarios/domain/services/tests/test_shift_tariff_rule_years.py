from decimal import Decimal

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.models import RouteSet
from scenarios.domain.services.shift_tariff_rule_years import (
    shift_tariff_rule_year_coefficients,
)
from scenarios.models import Scenario, TariffRule, TariffRuleYearValue

User = get_user_model()


class ShiftTariffRuleYearCoefficientsTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(login="shift_user", password="pass")
        self.route_set = RouteSet.objects.create(name="RS_SHIFT", code="RS_SHIFT")
        self.scenario = Scenario.objects.create(
            name="Shift scenario",
            start_year=2026,
            end_year=2035,
            route_set=self.route_set,
            author=self.user,
        )
        self.rule_with_coef = TariffRule.objects.create(
            scenario=self.scenario,
            name="With 2026",
            position=1,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=self.rule_with_coef,
            year=2026,
            coefficient=Decimal("1.0500"),
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=self.rule_with_coef,
            year=2027,
            coefficient=Decimal("1.0100"),
        )
        self.rule_without_source = TariffRule.objects.create(
            scenario=self.scenario,
            name="Without 2026",
            position=2,
        )
        TariffRuleYearValue.objects.create(
            tariff_rule=self.rule_without_source,
            year=2028,
            coefficient=Decimal("1.2000"),
        )

    def test_shifts_coefficients_and_resets_source_year(self) -> None:
        result = shift_tariff_rule_year_coefficients(
            scenario=self.scenario,
            from_year=2026,
            to_year=2027,
        )

        self.assertEqual(result.rules_total, 2)
        self.assertEqual(result.moved, 1)
        self.assertEqual(result.source_reset_to_one, 2)

        values = {
            (row.tariff_rule_id, row.year): row.coefficient
            for row in TariffRuleYearValue.objects.filter(
                tariff_rule__scenario=self.scenario
            )
        }
        self.assertEqual(values[(self.rule_with_coef.id, 2026)], Decimal("1"))
        self.assertEqual(values[(self.rule_with_coef.id, 2027)], Decimal("1.0500"))
        self.assertEqual(
            values[(self.rule_without_source.id, 2026)],
            Decimal("1"),
        )
        self.assertEqual(
            values[(self.rule_without_source.id, 2028)],
            Decimal("1.2000"),
        )
        self.assertNotIn((self.rule_without_source.id, 2027), values)

    def test_dry_run_does_not_write(self) -> None:
        shift_tariff_rule_year_coefficients(
            scenario=self.scenario,
            from_year=2026,
            to_year=2027,
            dry_run=True,
        )
        source = TariffRuleYearValue.objects.get(
            tariff_rule=self.rule_with_coef,
            year=2026,
        )
        self.assertEqual(source.coefficient, Decimal("1.0500"))

    def test_command_requires_distinct_years(self) -> None:
        with self.assertRaises(CommandError):
            call_command(
                "shift_tariff_rule_year_coefficients",
                scenario_id=self.scenario.id,
                from_year=2026,
                to_year=2026,
            )
