from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0031_cargo_code_charfield"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="is_model",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="Модельный маршрут IPEM",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="model_route",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="linked_operational_routes",
                to="core.route",
                verbose_name="Модельный маршрут",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["route_set", "is_model"],
                name="route_set_is_model_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["model_route"],
                name="route_model_route_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                condition=models.Q(("is_model", False)),
                fields=[
                    "route_set",
                    "origin_station",
                    "destination_station",
                    "cargo",
                    "wagon_kind",
                    "shipment_type",
                ],
                name="route_operational_link_idx",
            ),
        ),
        migrations.AddConstraint(
            model_name="route",
            constraint=models.CheckConstraint(
                condition=models.Q(("is_model", False))
                | models.Q(("model_route__isnull", True)),
                name="route_model_no_parent",
            ),
        ),
    ]
