from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0015_elasticity_lookup_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="scenario",
            name="consider_enterprise_load",
            field=models.BooleanField(
                default=True,
                verbose_name="Учитывать загрузку предприятия",
            ),
        ),
    ]
