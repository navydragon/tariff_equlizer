from django.db import migrations

from core.domain.cargo.etsng_categories import (
    CONSUMER_GOODS_POSITION_SPEC,
    FOOD_GOODS_POSITION_SPEC,
    expand_etsng_position_spec,
)
from core.domain.cargo.formatting import cargo_code_3_from_normalized


def _reclassify_cargo_category_flags(apps, schema_editor):
    Cargo = apps.get_model("core", "Cargo")
    consumer = expand_etsng_position_spec(CONSUMER_GOODS_POSITION_SPEC)
    food = expand_etsng_position_spec(FOOD_GOODS_POSITION_SPEC)

    for cargo in Cargo.objects.iterator():
        position = cargo_code_3_from_normalized(cargo.code)
        is_consumer = bool(position and position in consumer)
        is_food = bool(position and position in food)
        if cargo.is_consumer_goods != is_consumer or cargo.is_food_goods != is_food:
            cargo.is_consumer_goods = is_consumer
            cargo.is_food_goods = is_food
            cargo.save(update_fields=["is_consumer_goods", "is_food_goods"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0036_cargo_category_flags"),
    ]

    operations = [
        migrations.RunPython(
            _reclassify_cargo_category_flags,
            migrations.RunPython.noop,
        ),
    ]
