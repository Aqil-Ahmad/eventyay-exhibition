import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0001_initial"),
        ("exhibition", "0016_exhibitionproposal_accepted_profile_snapshot"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExhibitorVoucher",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "exhibitor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="vouchers",
                        to="exhibition.exhibitorinfo",
                    ),
                ),
                (
                    "voucher",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exhibitor_link",
                        to="base.voucher",
                    ),
                ),
            ],
            options={
                "ordering": ("-created",),
            },
        ),
    ]
