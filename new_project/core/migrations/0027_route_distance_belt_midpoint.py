from django.db import migrations, models

from core.domain.distance_belt import backfill_distance_belt_midpoint_db


def backfill_distance_belt_midpoint(apps, schema_editor):
    backfill_distance_belt_midpoint_db(schema_editor)


def add_distance_belt_midpoint_column(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor == "postgresql":
        schema_editor.execute(
            """
            ALTER TABLE core_route
            ADD COLUMN IF NOT EXISTS distance_belt_midpoint_km integer NULL
            CHECK (distance_belt_midpoint_km IS NULL OR distance_belt_midpoint_km >= 0)
            """
        )
        return
    if vendor == "sqlite":
        Route = apps.get_model("core", "Route")
        field = models.PositiveIntegerField(
            blank=True,
            null=True,
            verbose_name="Середина пояса дальности, км",
        )
        field.set_attributes_from_name("distance_belt_midpoint_km")
        schema_editor.add_field(Route, field)
        return

    Route = apps.get_model("core", "Route")
    field = models.PositiveIntegerField(
        blank=True,
        null=True,
        verbose_name="Середина пояса дальности, км",
    )
    field.set_attributes_from_name("distance_belt_midpoint_km")
    schema_editor.add_field(Route, field)


def drop_distance_belt_midpoint_column(apps, schema_editor):
    vendor = schema_editor.connection.vendor
    if vendor in ("postgresql", "sqlite"):
        schema_editor.execute(
            "ALTER TABLE core_route DROP COLUMN IF EXISTS distance_belt_midpoint_km"
        )
        return

    Route = apps.get_model("core", "Route")
    field = Route._meta.get_field("distance_belt_midpoint_km")
    schema_editor.remove_field(Route, field)


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0026_route_nominal_units"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name="route",
                    name="distance_belt_midpoint_km",
                    field=models.PositiveIntegerField(
                        blank=True,
                        null=True,
                        verbose_name="Середина пояса дальности, км",
                    ),
                ),
            ],
            database_operations=[
                migrations.RunPython(
                    add_distance_belt_midpoint_column,
                    drop_distance_belt_midpoint_column,
                ),
                migrations.RunPython(
                    backfill_distance_belt_midpoint,
                    migrations.RunPython.noop,
                ),
            ],
        ),
    ]
