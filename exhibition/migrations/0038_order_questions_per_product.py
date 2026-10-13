import django.db.models.deletion
from django.db import migrations, models


def assign_questions_to_products(apps, schema_editor):
    ExhibitionOrderQuestion = apps.get_model("exhibition", "ExhibitionOrderQuestion")
    ExhibitionProduct = apps.get_model("exhibition", "ExhibitionProduct")
    for question in ExhibitionOrderQuestion.objects.select_related("order_form"):
        question.event_id = question.order_form.event_id
        question.save(update_fields=["event"])
        question.products.set(ExhibitionProduct.objects.filter(order_form_id=question.order_form_id))


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0037_exhibition_order_forms'),
    ]

    operations = [
        migrations.AddField(
            model_name='exhibitorsettings',
            name='order_field_settings',
            field=models.JSONField(blank=True, default=dict),
        ),
        migrations.AddField(
            model_name='exhibitionorder',
            name='website',
            field=models.URLField(blank=True, max_length=500, verbose_name='Website'),
        ),
        migrations.AddField(
            model_name='exhibitionorder',
            name='billing_address',
            field=models.TextField(blank=True, verbose_name='Billing address'),
        ),
        migrations.AddField(
            model_name='exhibitionorder',
            name='vat_id',
            field=models.CharField(blank=True, max_length=64, verbose_name='VAT ID'),
        ),
        migrations.AddField(
            model_name='exhibitionorderquestion',
            name='event',
            field=models.ForeignKey(null=True, on_delete=django.db.models.deletion.CASCADE, related_name='exhibition_order_questions', to='base.event'),
        ),
        migrations.AddField(
            model_name='exhibitionorderquestion',
            name='products',
            field=models.ManyToManyField(blank=True, help_text='This field will be asked to buyers of the selected products.', related_name='order_questions', to='exhibition.exhibitionproduct', verbose_name='Products'),
        ),
        migrations.RunPython(assign_questions_to_products, migrations.RunPython.noop),
    ]
