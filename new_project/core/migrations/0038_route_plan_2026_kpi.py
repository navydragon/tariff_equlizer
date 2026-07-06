from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0037_reclassify_cargo_category_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="transport_volume_tons_plan_2026",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=18,
                null=True,
                verbose_name="Плановая погрузка 2026, т",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="freight_turnover_tkm_plan_2026",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=22,
                null=True,
                verbose_name="Плановый грузооборот 2026, т·км",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="freight_charge_rub_plan_2026",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=20,
                null=True,
                verbose_name="Плановые доходы 2026, руб.",
            ),
        ),
    ]
