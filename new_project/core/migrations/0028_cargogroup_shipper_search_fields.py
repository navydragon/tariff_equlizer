from django.db import migrations, models


def backfill_search_fields(apps, schema_editor) -> None:
    CargoGroup = apps.get_model("core", "CargoGroup")
    Shipper = apps.get_model("core", "Shipper")

    for group in CargoGroup.objects.all().iterator():
        group.name_search = (group.name or "").casefold()
        group.save(update_fields=["name_search"])

    for shipper in Shipper.objects.all().iterator():
        shipper.holding_search = (shipper.holding or "").casefold()
        shipper.save(update_fields=["holding_search"])


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0027_route_distance_belt_midpoint"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargogroup",
            name="name_search",
            field=models.CharField(
                db_index=True,
                default="",
                editable=False,
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="shipper",
            name="holding_search",
            field=models.CharField(
                db_index=True,
                default="",
                editable=False,
                max_length=255,
            ),
        ),
        migrations.RunPython(
            backfill_search_fields,
            migrations.RunPython.noop,
        ),
    ]
