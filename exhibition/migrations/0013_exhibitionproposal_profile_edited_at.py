from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0012_exhibitorsettings_call_private_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitionproposal",
            name="profile_edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
