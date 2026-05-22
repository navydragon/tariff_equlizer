from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0020_route_route_set_charge_idx"),
    ]

    operations = [
        migrations.CreateModel(
            name="Setting",
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
                    "code",
                    models.CharField(
                        db_index=True,
                        max_length=100,
                        unique=True,
                        verbose_name="Код",
                    ),
                ),
                (
                    "description",
                    models.TextField(blank=True, verbose_name="Описание"),
                ),
                (
                    "value",
                    models.CharField(max_length=255, verbose_name="Значение"),
                ),
            ],
            options={
                "verbose_name": "Настройка",
                "verbose_name_plural": "Настройки",
                "ordering": ["code"],
            },
        ),
    ]
