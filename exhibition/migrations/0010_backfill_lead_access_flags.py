from django.db import migrations


def backfill_lead_flags(apps, schema_editor):
    ExhibitorInfo = apps.get_model("exhibition", "ExhibitorInfo")
    ExhibitorInfo.objects.filter(is_exhibitor=True).update(
        lead_scanning_enabled=True,
        allow_lead_access=True,
    )


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0009_exhibitorinfo_active"),
    ]

    operations = [
        migrations.RunPython(backfill_lead_flags, migrations.RunPython.noop),
    ]
