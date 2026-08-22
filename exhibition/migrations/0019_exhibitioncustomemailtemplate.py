import django.db.models.deletion
import i18nfield.fields
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("base", "0043_remove_sendmail_from_plugins"),
        ("exhibition", "0018_exhibitordevice"),
    ]

    operations = [
        migrations.CreateModel(
            name="ExhibitionCustomEmailTemplate",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("name", models.CharField(max_length=190, verbose_name="Template name")),
                ("subject", i18nfield.fields.I18nCharField(max_length=255, verbose_name="Subject")),
                ("body", i18nfield.fields.I18nTextField(blank=True, verbose_name="Body")),
                ("created", models.DateTimeField(auto_now_add=True)),
                ("updated", models.DateTimeField(auto_now=True)),
                (
                    "event",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="exhibition_custom_email_templates",
                        to="base.event",
                    ),
                ),
            ],
            options={
                "verbose_name": "Custom email template",
                "verbose_name_plural": "Custom email templates",
                "ordering": ("name",),
            },
        ),
    ]
