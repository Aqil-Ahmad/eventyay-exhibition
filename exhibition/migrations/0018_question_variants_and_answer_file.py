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
                    ("string", "Text (one-line)"),
                    ("text", "Multi-line text"),
                    ("url", "URL"),
                    ("email", "Email address"),
                    ("phone", "Phone number"),
                    ("country", "Country code (ISO 3166-1 alpha-2)"),
                    ("date", "Date"),
                    ("time", "Time"),
                    ("datetime", "Date and time"),
                    ("file", "File upload"),
                    ("boolean", "Confirmation"),
                    ("choices", "Radio button (Choose one option)"),
                    ("multiple_choice", "Checkbox (Choose one or several options)"),
                    ("select", "Select (one option)"),
                ],
                default="string",
                max_length=32,
            ),
        ),
    ]
