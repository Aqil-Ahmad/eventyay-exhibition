import django.db.models.deletion
import exhibition.models
import i18nfield.fields
from django.db import migrations, models


def create_exhibitor_calls(apps, schema_editor):
    ExhibitorSettings = apps.get_model('exhibition', 'ExhibitorSettings')
    ExhibitionCall = apps.get_model('exhibition', 'ExhibitionCall')
    for settings in ExhibitorSettings.objects.all():
        ExhibitionCall.objects.get_or_create(
            event_id=settings.event_id,
            call_type='exhibitor',
            defaults={
                'enabled': settings.call_enabled,
                'headline': settings.call_headline,
                'text': settings.call_text,
                'deadline': settings.call_deadline,
                'hide_after_deadline': settings.call_hide_after_deadline,
                'field_settings': settings.proposal_field_settings or {},
            },
        )


class Migration(migrations.Migration):

    dependencies = [
        ('exhibition', '0007_offset_exhibition_question_positions'),
    ]

    operations = [
        migrations.CreateModel(
            name='ExhibitionCall',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('call_type', models.CharField(choices=[('exhibitor', 'Exhibitor'), ('sponsor', 'Sponsor')], max_length=20)),
                ('enabled', models.BooleanField(default=False)),
                ('headline', i18nfield.fields.I18nCharField(blank=True, max_length=200, verbose_name='Call headline')),
                ('text', i18nfield.fields.I18nTextField(blank=True, verbose_name='Call text')),
                ('deadline', models.DateTimeField(blank=True, null=True, verbose_name='Submission deadline')),
                ('hide_after_deadline', models.BooleanField(default=False)),
                ('field_settings', models.JSONField(default=exhibition.models.default_call_field_settings)),
                ('event', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name='exhibition_calls', to='base.event')),
            ],
            options={
                'unique_together': {('event', 'call_type')},
            },
        ),
        migrations.AddField(
            model_name='exhibitionproposal',
            name='call',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='proposals', to='exhibition.exhibitioncall'),
        ),
        migrations.RunPython(create_exhibitor_calls, migrations.RunPython.noop),
        migrations.RemoveField(model_name='exhibitorsettings', name='call_deadline'),
        migrations.RemoveField(model_name='exhibitorsettings', name='call_enabled'),
        migrations.RemoveField(model_name='exhibitorsettings', name='call_headline'),
        migrations.RemoveField(model_name='exhibitorsettings', name='call_hide_after_deadline'),
        migrations.RemoveField(model_name='exhibitorsettings', name='call_text'),
        migrations.RemoveField(model_name='exhibitorsettings', name='proposal_field_settings'),
    ]
