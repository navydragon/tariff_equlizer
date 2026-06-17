from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0029_route_holding_filter_indexes"),
    ]

    operations = [
        migrations.AddField(
            model_name="route",
            name="cargo_group_izpod",
            field=models.CharField(
                blank=True,
                default="",
                max_length=255,
                verbose_name="Группа груза (изпод)",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="cargo_code_3",
            field=models.CharField(
                blank=True,
                default="",
                max_length=3,
                verbose_name="Код груза 3 знака",
            ),
        ),
        migrations.AddField(
            model_name="route",
            name="cargo_code_izpod_3",
            field=models.CharField(
                blank=True,
                default="",
                max_length=3,
                verbose_name="Код груза из-под (3 знака)",
            ),
        ),
    ]
