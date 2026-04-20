from django.conf import settings
from django.db import models

from core.models import RouteSet


class Scenario(models.Model):
    name = models.CharField("Название", max_length=255)
    description = models.TextField("Описание", blank=True)
    start_year = models.IntegerField("Год начала", default=2025)
    end_year = models.IntegerField("Год окончания", default=2035)
    route_set = models.ForeignKey(
        RouteSet,
        verbose_name="Набор маршрутов",
        on_delete=models.PROTECT,
        related_name="scenarios",
    )
    author = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        verbose_name="Автор",
        on_delete=models.CASCADE,
        related_name="scenarios",
    )

    class Meta:
        verbose_name = "Сценарий"
        verbose_name_plural = "Сценарии"

    def __str__(self) -> str:
        return self.name


class BTDCategory(models.Model):
    """Категория базовых тарифных решений (BTD), упорядоченная по позиции в рамках сценария."""

    name = models.CharField("Название", max_length=255)
    scenario = models.ForeignKey(
        Scenario,
        verbose_name="Сценарий",
        on_delete=models.CASCADE,
        related_name="btd_categories",
    )
    position = models.PositiveIntegerField("Позиция")

    class Meta:
        verbose_name = "Категория базовых тарифных решений"
        verbose_name_plural = "Категории базовых тарифных решений"
        ordering = ["scenario", "position", "id"]
        unique_together = ("scenario", "position")

    def __str__(self) -> str:
        return self.name


class BTDCategoryValue(models.Model):
    """Значение категории базовых тарифных решений по годам сценария."""

    scenario = models.ForeignKey(
        Scenario,
        verbose_name="Сценарий",
        on_delete=models.CASCADE,
        related_name="btd_values",
    )
    category = models.ForeignKey(
        BTDCategory,
        verbose_name="Категория",
        on_delete=models.CASCADE,
        related_name="values",
    )
    year = models.IntegerField("Год")
    value = models.DecimalField("Значение", max_digits=10, decimal_places=4)

    class Meta:
        verbose_name = "Значение категории базовых тарифных решений"
        verbose_name_plural = "Значения категорий базовых тарифных решений"
        unique_together = ("scenario", "category", "year")
        ordering = ["scenario", "category", "year"]

    def __str__(self) -> str:
        return f"{self.category} {self.year}: {self.value}"


class TariffRule(models.Model):
    scenario = models.ForeignKey(
        Scenario,
        verbose_name="Сценарий",
        on_delete=models.CASCADE,
        related_name="tariff_rules",
    )
    name = models.CharField("Название решения", max_length=255)
    base_percent = models.DecimalField(
        "% покрытия базы",
        max_digits=7,
        decimal_places=4,
        default=100,
    )
    position = models.PositiveIntegerField("Позиция", default=0)
    created_at = models.DateTimeField("Создано", auto_now_add=True)
    updated_at = models.DateTimeField("Обновлено", auto_now=True)

    class Meta:
        verbose_name = "Отдельное тарифное решение"
        verbose_name_plural = "Отдельные тарифные решения"
        ordering = ["scenario", "position", "id"]

    def __str__(self) -> str:
        return self.name


class TariffRuleCondition(models.Model):
    class Operator(models.TextChoices):
        INCLUDE = "include", "включает"
        EXCLUDE = "exclude", "не включает"
        LT = "lt", "<"
        GT = "gt", ">"

    tariff_rule = models.ForeignKey(
        TariffRule,
        verbose_name="Тарифное решение",
        on_delete=models.CASCADE,
        related_name="conditions",
    )
    parameter = models.CharField("Параметр", max_length=64)
    operator = models.CharField(
        "Оператор",
        max_length=16,
        choices=Operator.choices,
        default=Operator.INCLUDE,
    )
    values = models.JSONField("Значения", default=list, blank=True)
    position = models.PositiveIntegerField("Позиция", default=0)

    class Meta:
        verbose_name = "Условие тарифного решения"
        verbose_name_plural = "Условия тарифных решений"
        ordering = ["tariff_rule", "position", "id"]


class TariffRuleYearValue(models.Model):
    tariff_rule = models.ForeignKey(
        TariffRule,
        verbose_name="Тарифное решение",
        on_delete=models.CASCADE,
        related_name="year_values",
    )
    year = models.IntegerField("Год")
    coefficient = models.DecimalField(
        "Коэффициент",
        max_digits=10,
        decimal_places=4,
        default=1,
    )

    class Meta:
        verbose_name = "Коэффициент тарифного решения по году"
        verbose_name_plural = "Коэффициенты тарифных решений по годам"
        constraints = [
            models.UniqueConstraint(
                fields=["tariff_rule", "year"],
                name="uniq_tariff_rule_year",
            )
        ]

