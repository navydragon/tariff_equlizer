from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0034_route_turnover_change_coefs"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="skip_elasticity",
            field=models.BooleanField(
                default=True,
                verbose_name="Не учитывать эластичность",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="elasticity_source",
            field=models.CharField(
                choices=[
                    ("none", "Не рассчитывается"),
                    ("direct_model", "Модельный маршрут"),
                    ("holding_aggregate", "Среднее по холдингу"),
                    ("cargo_group_aggregate", "Среднее по группе груза"),
                ],
                default="none",
                max_length=32,
                verbose_name="Источник эластичности",
            ),
        ),
    ]
