from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0023_scenario_retention_combined"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenario",
            name="ignore_own_axles_cargo",
            field=models.BooleanField(
                default=False,
                verbose_name="Игнорировать грузы на своих осях",
            ),
        ),
    ]

