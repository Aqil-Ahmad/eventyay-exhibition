import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0035_exhibitionquota'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exhibitionorderposition',
            name='product',
            field=models.ForeignKey(on_delete=django.db.models.deletion.RESTRICT, related_name='order_positions', to='exhibition.exhibitionproduct', verbose_name='Product'),
        ),
    ]
