from django.db import migrations, models


def _postgres_fk_name(cursor) -> str | None:
    cursor.execute(
        """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class child ON c.conrelid = child.oid
        JOIN pg_class parent ON c.confrelid = parent.oid
        WHERE child.relname = 'core_route'
          AND parent.relname = 'core_cargo'
          AND c.contype = 'f'
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _postgres_check_constraint(cursor) -> str | None:
    cursor.execute(
        """
        SELECT c.conname
        FROM pg_constraint c
        JOIN pg_class rel ON c.conrelid = rel.oid
        WHERE rel.relname = 'core_cargo'
          AND c.contype = 'c'
          AND pg_get_constraintdef(c.oid) LIKE '%code%'
        LIMIT 1
        """
    )
    row = cursor.fetchone()
    return row[0] if row else None


def _forward_cargo_code_to_char(apps, schema_editor):
    connection = schema_editor.connection
    vendor = connection.vendor
    with connection.cursor() as cursor:
        if vendor == "sqlite":
            cursor.execute(
                "UPDATE core_cargo SET code = printf('%06d', code)"
            )
            cursor.execute(
                "UPDATE core_route SET cargo_id = printf('%06d', cargo_id) "
                "WHERE cargo_id IS NOT NULL"
            )
            return

        if vendor == "postgresql":
            fk_name = _postgres_fk_name(cursor)
            check_name = _postgres_check_constraint(cursor)
            if fk_name:
                cursor.execute(
                    f'ALTER TABLE core_route DROP CONSTRAINT "{fk_name}"'
                )
            if check_name:
                cursor.execute(
                    f'ALTER TABLE core_cargo DROP CONSTRAINT "{check_name}"'
                )
            cursor.execute(
                """
                ALTER TABLE core_cargo
                ALTER COLUMN code TYPE varchar(6)
                USING LPAD(code::text, 6, '0')
                """
            )
            cursor.execute(
                """
                ALTER TABLE core_route
                ALTER COLUMN cargo_id TYPE varchar(6)
                USING LPAD(cargo_id::text, 6, '0')
                """
            )
            if fk_name:
                cursor.execute(
                    f"""
                    ALTER TABLE core_route
                    ADD CONSTRAINT "{fk_name}"
                    FOREIGN KEY (cargo_id)
                    REFERENCES core_cargo(code)
                    DEFERRABLE INITIALLY DEFERRED
                    """
                )
            return

        cursor.execute(
            "UPDATE core_cargo SET code = LPAD(CAST(code AS CHAR), 6, '0')"
        )
        cursor.execute(
            "UPDATE core_route SET cargo_id = LPAD(CAST(cargo_id AS CHAR), 6, '0') "
            "WHERE cargo_id IS NOT NULL"
        )


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0030_route_cargo_izpod_fields"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[
                migrations.RunPython(
                    _forward_cargo_code_to_char,
                    migrations.RunPython.noop,
                ),
            ],
            state_operations=[
                migrations.AlterField(
                    model_name="cargo",
                    name="code",
                    field=models.CharField(
                        max_length=6,
                        primary_key=True,
                        serialize=False,
                        verbose_name="Код ETSNG",
                    ),
                ),
            ],
        ),
        migrations.AlterField(
            model_name="cargo",
            name="code",
            field=models.CharField(
                max_length=6,
                primary_key=True,
                serialize=False,
                verbose_name="Код ETSNG",
            ),
        ),
    ]
