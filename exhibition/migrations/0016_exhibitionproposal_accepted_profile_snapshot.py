from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0015_backfill_lead_access_flags"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitionproposal",
            name="accepted_profile_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
