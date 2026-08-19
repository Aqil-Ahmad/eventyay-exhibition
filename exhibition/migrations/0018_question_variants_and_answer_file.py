from django.db import migrations, models

import exhibition.models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0017_exhibitorvoucher"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitionanswer",
            name="file",
            field=models.FileField(blank=True, null=True, upload_to=exhibition.models.exhibition_answer_path),
        ),
        migrations.AlterField(
            model_name="exhibitionquestion",
            name="variant",
            field=models.CharField(
                choices=[
                    ("number", "Number"),
                    ("string", "Text (one line)"),
                    ("text", "Multiline text"),
                    ("url", "URL"),
                    ("email", "Email address"),
                    ("boolean", "Confirm Checkbox"),
                    ("choices", "Radio button (Choose one option)"),
                    ("select", "Dropdown (Choose one option)"),
                    ("multiple_choice", "Checkbox (Choose one or several options)"),
                    ("file", "File upload"),
                    ("date", "Date"),
                    ("time", "Time"),
                    ("datetime", "Date and time"),
                    ("country", "Country code (ISO 3166-1 alpha-2)"),
                    ("phone", "Phone number"),
                ],
                default="string",
                max_length=32,
            ),
        ),
    ]
