from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0021_alter_scenario_consider_turnover_changes"),
    ]

    operations = [
        migrations.AddField(
            model_name="tariffrule",
            name="is_enabled",
            field=models.BooleanField(default=True, verbose_name="Включено"),
        ),
    ]
