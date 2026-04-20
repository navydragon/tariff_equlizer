from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):
    dependencies = [
        ("scenarios", "0006_scenario_route_set"),
    ]

    operations = [
        migrations.CreateModel(
            name="TariffRule",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=255, verbose_name="Название решения")),
                ("base_percent", models.DecimalField(decimal_places=4, default=100, max_digits=6, verbose_name="% покрытия базы")),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Позиция")),
                ("created_at", models.DateTimeField(auto_now_add=True, verbose_name="Создано")),
                ("updated_at", models.DateTimeField(auto_now=True, verbose_name="Обновлено")),
                ("scenario", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="tariff_rules", to="scenarios.scenario", verbose_name="Сценарий")),
            ],
            options={
                "verbose_name": "Отдельное тарифное решение",
                "verbose_name_plural": "Отдельные тарифные решения",
                "ordering": ["scenario", "position", "id"],
            },
        ),
        migrations.CreateModel(
            name="TariffRuleCondition",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("parameter", models.CharField(max_length=64, verbose_name="Параметр")),
                ("operator", models.CharField(choices=[("include", "включает"), ("exclude", "не включает"), ("lt", "<"), ("gt", ">")], default="include", max_length=16, verbose_name="Оператор")),
                ("values", models.JSONField(blank=True, default=list, verbose_name="Значения")),
                ("position", models.PositiveIntegerField(default=0, verbose_name="Позиция")),
                ("tariff_rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="conditions", to="scenarios.tariffrule", verbose_name="Тарифное решение")),
            ],
            options={
                "verbose_name": "Условие тарифного решения",
                "verbose_name_plural": "Условия тарифных решений",
                "ordering": ["tariff_rule", "position", "id"],
            },
        ),
        migrations.CreateModel(
            name="TariffRuleYearValue",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("year", models.IntegerField(verbose_name="Год")),
                ("coefficient", models.DecimalField(decimal_places=4, default=1, max_digits=10, verbose_name="Коэффициент")),
                ("tariff_rule", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="year_values", to="scenarios.tariffrule", verbose_name="Тарифное решение")),
            ],
            options={
                "verbose_name": "Коэффициент тарифного решения по году",
                "verbose_name_plural": "Коэффициенты тарифных решений по годам",
            },
        ),
        migrations.AddConstraint(
            model_name="tariffruleyearvalue",
            constraint=models.UniqueConstraint(fields=("tariff_rule", "year"), name="uniq_tariff_rule_year"),
        ),
    ]

