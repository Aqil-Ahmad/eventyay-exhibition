import django.db.models.deletion
import exhibition.models
from django.db import migrations, models


def give_each_order_its_own_secret(apps, schema_editor):
    ExhibitionOrder = apps.get_model('exhibition', 'ExhibitionOrder')
    for order in ExhibitionOrder.objects.only('pk'):
        order.secret = exhibition.models.generate_order_secret()
        order.save(update_fields=['secret'])


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0040_merge_request_confirmed_and_orders'),
    ]

    operations = [
        migrations.AddField(
            model_name='exhibitionorder',
            name='secret',
            field=models.CharField(default=exhibition.models.generate_order_secret, max_length=32),
        ),
        migrations.RunPython(give_each_order_its_own_secret, migrations.RunPython.noop),
        migrations.AddField(
            model_name='exhibitionorder',
            name='organization',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='exhibition_orders', to='exhibition.exhibitorinfo', verbose_name='Organization'),
        ),
        migrations.AddField(
            model_name='exhibitorinfo',
            name='source_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='+', to='exhibition.exhibitionorder', verbose_name='Created by order'),
        ),
        migrations.AddField(
            model_name='exhibitionemailqueue',
            name='exhibition_order',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='emails', to='exhibition.exhibitionorder'),
        ),
    ]
