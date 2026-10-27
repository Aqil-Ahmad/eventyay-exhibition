import django.core.validators
import i18nfield.fields
from django.db import migrations, models

import exhibition.models


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0032_exhibitionemaildraft"),
    ]

    operations = [
        migrations.AddField(
            model_name="exhibitorsettings",
            name="layout_image",
            field=models.ImageField(
                blank=True,
                help_text=(
                    "A floor plan of the exhibition area, shown below the exhibitor list on the public Exhibition "
                    "page. PNG, JPG or WebP."
                ),
                null=True,
                upload_to=exhibition.models.exhibition_layout_path,
                validators=[django.core.validators.FileExtensionValidator(("png", "jpg", "jpeg", "webp"))],
                verbose_name="Exhibition layout",
            ),
        ),
        migrations.AddField(
            model_name="exhibitorsettings",
            name="layout_caption",
            field=i18nfield.fields.I18nCharField(
                blank=True,
                help_text='Shown under the layout, such as "Hall 1, ground floor".',
                max_length=200,
                verbose_name="Layout caption",
            ),
        ),
    ]
