import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0001_initial"),
        ("exhibition", "0017_exhibitorvoucher"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExhibitorDevice",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("created", models.DateTimeField(auto_now_add=True)),
                (
                    "exhibitor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="devices",
                        to="exhibition.exhibitorinfo",
                    ),
                ),
                (
                    "device",
                    models.OneToOneField(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exhibitor_link",
                        to="base.device",
                    ),
                ),
            ],
            options={
                "ordering": ("created", "pk"),
            },
        ),
    ]
