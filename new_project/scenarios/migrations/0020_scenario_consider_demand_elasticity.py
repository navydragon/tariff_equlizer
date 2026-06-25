from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scenarios", "0019_scenario_consider_turnover_changes"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenario",
            name="consider_demand_elasticity",
            field=models.BooleanField(
                default=False,
                verbose_name="Учитывать эластичность спроса",
            ),
        ),
    ]
