from django.db import migrations, models

import exhibition.models


def assign_tokens(apps, schema_editor):
    ExhibitorInfo = apps.get_model("exhibition", "ExhibitorInfo")
    for exhibitor in ExhibitorInfo.objects.filter(voucher_link_token__isnull=True).only("pk"):
        exhibitor.voucher_link_token = exhibition.models.generate_voucher_link_token()
        exhibitor.save(update_fields=["voucher_link_token"])


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0030_exhibitorinfo_published"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitorinfo",
            name="voucher_link_token",
            field=models.CharField(editable=False, max_length=64, null=True),
        ),
        migrations.RunPython(assign_tokens, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="exhibitorinfo",
            name="voucher_link_token",
            field=models.CharField(
                default=exhibition.models.generate_voucher_link_token,
                editable=False,
                max_length=64,
                unique=True,
            ),
        ),
    ]
