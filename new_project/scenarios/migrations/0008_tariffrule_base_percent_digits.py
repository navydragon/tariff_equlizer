from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("scenarios", "0007_tariff_rules"),
    ]

    operations = [
        migrations.AlterField(
            model_name="tariffrule",
            name="base_percent",
            field=models.DecimalField(
                decimal_places=4,
                default=100,
                max_digits=7,
                verbose_name="% покрытия базы",
            ),
        ),
    ]

