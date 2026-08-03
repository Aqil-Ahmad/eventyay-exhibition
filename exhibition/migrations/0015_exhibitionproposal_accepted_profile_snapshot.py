from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0014_exhibitionproposal_profile_edited_at"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitionproposal",
            name="accepted_profile_snapshot",
            field=models.JSONField(blank=True, null=True),
        ),
    ]
