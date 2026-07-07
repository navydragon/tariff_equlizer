from django.db import migrations, models


def migrate_all_to_combined(apps, schema_editor):
    Scenario = apps.get_model("scenarios", "Scenario")
    Scenario.objects.all().update(retention_coefficient_mode="combined")


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0022_tariffrule_is_enabled"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scenario",
            name="retention_coefficient_mode",
            field=models.CharField(
                choices=[
                    ("combined", "Комбинированный (как в IPEM)"),
                    ("absolute", "По текущей маржинальности"),
                    ("relative_to_base", "Относительно базовой маржинальности"),
                ],
                default="combined",
                max_length=32,
                verbose_name="Прогноз коэффициента сохранения грузовой базы",
            ),
        ),
        migrations.RunPython(
            migrate_all_to_combined,
            migrations.RunPython.noop,
        ),
    ]
