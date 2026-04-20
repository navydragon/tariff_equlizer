from django.contrib import admin

from .models import (
    Scenario,
    TariffRule,
    TariffRuleCondition,
    TariffRuleYearValue,
)


@admin.register(Scenario)
class ScenarioAdmin(admin.ModelAdmin):
    list_display = ("name", "author")
    search_fields = ("name", "author__login", "author__last_name", "author__first_name")


class TariffRuleConditionInline(admin.TabularInline):
    model = TariffRuleCondition
    extra = 0


class TariffRuleYearValueInline(admin.TabularInline):
    model = TariffRuleYearValue
    extra = 0


@admin.register(TariffRule)
class TariffRuleAdmin(admin.ModelAdmin):
    list_display = ("name", "scenario", "base_percent", "position", "updated_at")
    list_filter = ("scenario",)
    search_fields = ("name", "scenario__name")
    ordering = ("scenario", "position", "id")
    inlines = (TariffRuleConditionInline, TariffRuleYearValueInline)
