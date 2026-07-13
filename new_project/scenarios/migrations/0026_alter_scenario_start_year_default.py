from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0025_alter_scenario_retention_coefficient_mode"),
    ]

    operations = [
        migrations.AlterField(
            model_name="scenario",
            name="start_year",
            field=models.IntegerField(default=2026, verbose_name="Год начала"),
        ),
    ]
