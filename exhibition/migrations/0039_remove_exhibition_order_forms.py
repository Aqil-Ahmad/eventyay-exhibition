import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0038_order_questions_per_product'),
    ]

    operations = [
        migrations.AlterField(
            model_name='exhibitionorderquestion',
            name='event',
            field=models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exhibition_order_questions', to='base.event'),
        ),
        migrations.RemoveField(
            model_name='exhibitionorderquestion',
            name='booth_only',
        ),
        migrations.RemoveField(
            model_name='exhibitionorderquestion',
            name='order_form',
        ),
        migrations.RemoveField(
            model_name='exhibitionproduct',
            name='order_form',
        ),
        migrations.DeleteModel(
            name='ExhibitionOrderForm',
        ),
    ]
