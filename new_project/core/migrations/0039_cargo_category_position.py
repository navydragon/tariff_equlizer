from django.db import migrations, models


def _seed_cargo_category_positions(apps, schema_editor):
    CargoCategoryPosition = apps.get_model("core", "CargoCategoryPosition")
    from core.domain.cargo.etsng_categories import (
        CONSUMER_GOODS_POSITION_SPEC,
        FOOD_GOODS_POSITION_SPEC,
        expand_etsng_position_spec,
    )

    consumer_positions = expand_etsng_position_spec(CONSUMER_GOODS_POSITION_SPEC)
    food_positions = expand_etsng_position_spec(FOOD_GOODS_POSITION_SPEC)

    to_create = [
        CargoCategoryPosition(category="consumer_goods", position=position)
        for position in sorted(consumer_positions)
    ]
    to_create.extend(
        CargoCategoryPosition(category="food_goods", position=position)
        for position in sorted(food_positions)
    )
    CargoCategoryPosition.objects.bulk_create(to_create, ignore_conflicts=True)


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0038_route_plan_2026_kpi"),
    ]

    operations = [
        migrations.CreateModel(
            name="CargoCategoryPosition",
            fields=[
                (
                    "id",
                    models.BigAutoField(
                        auto_created=True,
                        primary_key=True,
                        serialize=False,
                        verbose_name="ID",
                    ),
                ),
                (
                    "category",
                    models.CharField(
                        choices=[
                            ("consumer_goods", "Потребительские товары"),
                            ("food_goods", "Продовольственные товары"),
                        ],
                        db_index=True,
                        max_length=32,
                        verbose_name="Категория",
                    ),
                ),
                (
                    "position",
                    models.CharField(max_length=3, verbose_name="Позиция ЕТСНГ"),
                ),
            ],
            options={
                "verbose_name": "Позиция специального набора",
                "verbose_name_plural": "Позиции специальных наборов",
                "ordering": ["category", "position"],
            },
        ),
        migrations.AddConstraint(
            model_name="cargocategoryposition",
            constraint=models.UniqueConstraint(
                fields=("category", "position"),
                name="uniq_cargo_category_position",
            ),
        ),
        migrations.RunPython(
            _seed_cargo_category_positions,
            migrations.RunPython.noop,
        ),
    ]
