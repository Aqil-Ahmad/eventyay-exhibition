from django.db import migrations, models

import exhibition.models


def add_name_email_to_existing(apps, schema_editor):
    ExhibitorSettings = apps.get_model("exhibition", "ExhibitorSettings")
    for settings in ExhibitorSettings.objects.all():
        allowed = list(settings.allowed_fields or [])
        changed = False
        for field in ("attendee_name", "attendee_email"):
            if field not in allowed:
                allowed.append(field)
                changed = True
        if changed:
            settings.allowed_fields = allowed
            settings.save(update_fields=["allowed_fields"])


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0010_exhibitorinfo_exhibitor_position_and_more'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exhibitorsettings',
            name='allowed_fields',
            field=models.JSONField(default=exhibition.models.default_allowed_fields),
        ),
        migrations.RunPython(add_name_email_to_existing, migrations.RunPython.noop),
    ]
