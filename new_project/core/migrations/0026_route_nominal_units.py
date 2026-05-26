from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0025_route_rzd_attributes"),
    ]

    operations = [
        migrations.RemoveIndex(
            model_name="route",
            name="route_set_charge_idx",
        ),
        migrations.RenameField(
            model_name="route",
            old_name="transport_volume_mln_tons",
            new_name="transport_volume_tons",
        ),
        migrations.RenameField(
            model_name="route",
            old_name="freight_turnover_bln_tkm",
            new_name="freight_turnover_tkm",
        ),
        migrations.RenameField(
            model_name="route",
            old_name="freight_charge_ths_rub",
            new_name="freight_charge_rub",
        ),
        migrations.AlterField(
            model_name="route",
            name="transport_volume_tons",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=18,
                null=True,
                verbose_name="Объём перевозок, т",
            ),
        ),
        migrations.AlterField(
            model_name="route",
            name="freight_turnover_tkm",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                max_digits=22,
                null=True,
                verbose_name="Грузооборот, т·км",
            ),
        ),
        migrations.AlterField(
            model_name="route",
            name="freight_charge_rub",
            field=models.DecimalField(
                blank=True,
                decimal_places=2,
                max_digits=20,
                null=True,
                verbose_name="Провозная плата, руб.",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["route_set", "freight_charge_rub"],
                name="route_set_charge_idx",
            ),
        ),
    ]
