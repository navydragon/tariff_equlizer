from django.db import migrations, models


def _backfill_cargo_category_flags(apps, schema_editor):
    Cargo = apps.get_model("core", "Cargo")
    from core.domain.cargo.etsng_categories import classify_cargo_flags

    for cargo in Cargo.objects.iterator():
        is_consumer, is_food = classify_cargo_flags(cargo.code)
        if cargo.is_consumer_goods != is_consumer or cargo.is_food_goods != is_food:
            cargo.is_consumer_goods = is_consumer
            cargo.is_food_goods = is_food
            cargo.save(update_fields=["is_consumer_goods", "is_food_goods"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0035_route_elasticity_fields"),
    ]

    operations = [
        migrations.AddField(
            model_name="cargo",
            name="is_consumer_goods",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="Потребительские товары",
            ),
        ),
        migrations.AddField(
            model_name="cargo",
            name="is_food_goods",
            field=models.BooleanField(
                db_index=True,
                default=False,
                verbose_name="Продовольственные товары",
            ),
        ),
        migrations.RunPython(
            _backfill_cargo_category_flags,
            migrations.RunPython.noop,
        ),
    ]
