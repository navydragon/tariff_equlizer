from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0032_route_model_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="enterprise_load_coefficient",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=6,
                null=True,
                verbose_name="Коэффициент загрузки предприятия",
            ),
        ),
    ]
