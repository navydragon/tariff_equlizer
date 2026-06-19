from django.db import migrations, models


def set_relative_to_base_default(apps, schema_editor):
    Scenario = apps.get_model("scenarios", "Scenario")
    Scenario.objects.filter(retention_coefficient_mode="absolute").update(
        retention_coefficient_mode="relative_to_base",
    )


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0017_scenario_retention_coefficient_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scenario",
            name="retention_coefficient_mode",
            field=models.CharField(
                choices=[
                    ("absolute", "По текущей маржинальности"),
                    ("relative_to_base", "Относительно базовой маржинальности"),
                ],
                default="relative_to_base",
                max_length=32,
                verbose_name="Прогноз коэффициента сохранения грузовой базы",
            ),
        ),
        migrations.RunPython(
            set_relative_to_base_default,
            migrations.RunPython.noop,
        ),
    ]
