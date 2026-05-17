from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0019_route_transport_work_indicators"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["route_set", "freight_charge_ths_rub"],
                name="route_set_charge_idx",
            ),
        ),
    ]
