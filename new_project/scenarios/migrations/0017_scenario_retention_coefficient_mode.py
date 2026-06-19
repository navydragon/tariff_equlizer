from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0016_scenario_consider_enterprise_load"),
    ]

    operations = [
        migrations.AddField(
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
    ]
