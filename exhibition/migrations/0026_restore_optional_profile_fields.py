import django.db.models.deletion
from django.db import migrations, models

import exhibition.models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0025_voucher_email_attachment"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitorinfo",
            name="contact_url",
            field=models.URLField(blank=True, null=True, verbose_name="Contact URL"),
        ),
        migrations.AddField(
            model_name="exhibitorinfo",
            name="video_url",
            field=models.URLField(blank=True, null=True, verbose_name="Video URL"),
        ),
        migrations.AddField(
            model_name="exhibitorinfo",
            name="slides",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=exhibition.models.exhibitor_slides_path,
                verbose_name="Slides",
            ),
        ),
        migrations.AddField(
            model_name="exhibitorinfo",
            name="slides_url",
            field=models.URLField(blank=True, null=True, verbose_name="Slides URL"),
        ),
        migrations.AddField(
            model_name="exhibitionproposal",
            name="contact_url",
            field=models.URLField(blank=True, null=True, verbose_name="Contact URL"),
        ),
        migrations.AddField(
            model_name="exhibitionproposal",
            name="video_url",
            field=models.URLField(blank=True, null=True, verbose_name="Video URL"),
        ),
        migrations.AddField(
            model_name="exhibitionproposal",
            name="slides",
            field=models.FileField(
                blank=True,
                null=True,
                upload_to=exhibition.models.proposal_slides_path,
                verbose_name="Slides",
            ),
        ),
        migrations.AddField(
            model_name="exhibitionproposal",
            name="slides_url",
            field=models.URLField(blank=True, null=True, verbose_name="Slides URL"),
        ),
        migrations.AddField(
            model_name="exhibitionproposal",
            name="notes",
            field=models.TextField(blank=True, null=True, verbose_name="Message to the organizers"),
        ),
        migrations.CreateModel(
            name="ExhibitorExtraLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=120, verbose_name="Label")),
                ("url", models.URLField(verbose_name="URL")),
                (
                    "exhibitor",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_links",
                        to="exhibition.exhibitorinfo",
                    ),
                ),
            ],
            options={
                "ordering": ("label", "url"),
            },
        ),
        migrations.CreateModel(
            name="ExhibitionProposalExtraLink",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name="ID")),
                ("label", models.CharField(max_length=120, verbose_name="Label")),
                ("url", models.URLField(verbose_name="URL")),
                (
                    "proposal",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="extra_links",
                        to="exhibition.exhibitionproposal",
                    ),
                ),
            ],
            options={
                "ordering": ("label", "url"),
            },
        ),
    ]
