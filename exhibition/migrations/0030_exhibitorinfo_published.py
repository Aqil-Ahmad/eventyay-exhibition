from django.db import migrations, models


def publish_visible_organizations(apps, schema_editor):
    """Everything visible on the public site today stays visible after the split."""
    ExhibitorInfo = apps.get_model("exhibition", "ExhibitorInfo")
    ExhibitorInfo.objects.filter(active=True).update(published=True)


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0029_organization_banner_and_request_rename"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitorinfo",
            name="published",
            field=models.BooleanField(
                default=False,
                help_text="Only published organizations appear on the public event website.",
                verbose_name="Published",
            ),
        ),
        migrations.RunPython(publish_visible_organizations, migrations.RunPython.noop),
    ]
