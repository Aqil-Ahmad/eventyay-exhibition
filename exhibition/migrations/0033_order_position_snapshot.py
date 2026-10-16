import i18nfield.fields
from django.db import migrations, models


def copy_product_details(apps, schema_editor):
    ExhibitionOrderPosition = apps.get_model('exhibition', 'ExhibitionOrderPosition')
    positions = list(ExhibitionOrderPosition.objects.select_related('product'))
    for position in positions:
        position.name = position.product.name
        position.purpose = position.product.purpose
        position.includes_booth = position.product.includes_booth
    ExhibitionOrderPosition.objects.bulk_update(positions, ['name', 'purpose', 'includes_booth'])


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0032_exhibition_sales'),
    ]

    operations = [
        migrations.AddField(
            model_name='exhibitionorderposition',
            name='name',
            field=i18nfield.fields.I18nCharField(default='', max_length=255, verbose_name='Product name'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='exhibitionorderposition',
            name='purpose',
            field=models.CharField(choices=[('exhibition', 'Exhibition'), ('sponsorship', 'Sponsorship')], default='', max_length=16, verbose_name='Product purpose'),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='exhibitionorderposition',
            name='includes_booth',
            field=models.BooleanField(default=False, verbose_name='Includes exhibition booth'),
        ),
        migrations.RunPython(copy_product_details, migrations.RunPython.noop),
    ]
