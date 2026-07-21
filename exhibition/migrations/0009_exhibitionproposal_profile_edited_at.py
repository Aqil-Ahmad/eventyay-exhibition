from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0008_exhibitionemailqueue"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitionproposal",
            name="profile_edited_at",
            field=models.DateTimeField(blank=True, null=True),
        ),
    ]
