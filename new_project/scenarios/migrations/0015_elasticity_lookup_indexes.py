from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("scenarios", "0014_elasticity_sets"),
    ]

    operations = [
        migrations.AddIndex(
            model_name="elasticityrule",
            index=models.Index(
                fields=["elasticity_set", "position", "id"],
                name="elast_rule_set_pos_idx",
            ),
        ),
        migrations.AddIndex(
            model_name="elasticityrulepoint",
            index=models.Index(
                fields=["rule", "-marginality"],
                name="elast_pt_rule_marg_d_idx",
            ),
        ),
    ]
