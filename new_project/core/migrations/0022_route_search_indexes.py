from django.db import migrations, models


def create_route_code_trgm_index(apps, schema_editor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("CREATE EXTENSION IF NOT EXISTS pg_trgm")
        cursor.execute(
            """
            CREATE INDEX IF NOT EXISTS route_code_trgm_idx
            ON core_route USING gin (route_code gin_trgm_ops)
            """
        )


def drop_route_code_trgm_index(apps, schema_editor) -> None:
    if schema_editor.connection.vendor != "postgresql":
        return
    with schema_editor.connection.cursor() as cursor:
        cursor.execute("DROP INDEX IF EXISTS route_code_trgm_idx")


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0021_setting"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="route",
            index=models.Index(fields=["route_set", "id"], name="route_set_id_idx"),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["route_set", "origin_station"],
                name="route_set_origin_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="route",
            index=models.Index(
                fields=["route_set", "destination_station"],
                name="route_set_dest_idx",
            ),
        ),
        migrations.RunPython(
            create_route_code_trgm_index,
            drop_route_code_trgm_index,
        ),
    ]
