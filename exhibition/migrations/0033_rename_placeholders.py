from django.db import migrations
from eventyay.helpers.placeholders import rename_placeholder
from i18nfield.strings import LazyI18nString

RENAMES = (("name", "applicant_name"), ("voucher_list", "voucher_details"))
FIELDS = {"ExhibitionCustomEmailTemplate": ("subject", "body"), "ExhibitionEmailDraft": ("subject", "body")}


def rename_all(text, renames):
    for old, new in renames:
        text = rename_placeholder(text, old, new)
    return text


def renamed(value, renames):
    data = value.data if isinstance(value, LazyI18nString) else value
    if isinstance(data, dict):
        return LazyI18nString({lang: rename_all(text, renames) for lang, text in data.items()})
    if isinstance(data, str):
        return LazyI18nString(rename_all(data, renames))
    return value


def rename_placeholders(apps, renames):
    settings_store = apps.get_model("base", "Event_SettingsStore")
    for setting in settings_store.objects.filter(key__startswith="exhibition_mail_"):
        value = rename_all(setting.value, renames)
        if value != setting.value:
            setting.value = value
            setting.save(update_fields=["value"])

    for model_name, fields in FIELDS.items():
        model = apps.get_model("exhibition", model_name)
        for row in model.objects.all().iterator():
            changed = []
            for field in fields:
                value = getattr(row, field)
                if value is None:
                    continue
                new_value = renamed(value, renames)
                if new_value.data != (value.data if isinstance(value, LazyI18nString) else value):
                    setattr(row, field, new_value)
                    changed.append(field)
            if changed:
                row.save(update_fields=changed)


def forwards(apps, schema_editor):
    rename_placeholders(apps, RENAMES)


def backwards(apps, schema_editor):
    rename_placeholders(apps, [(new, old) for old, new in RENAMES])


class Migration(migrations.Migration):
    dependencies = [
        ("exhibition", "0032_exhibitionemaildraft"),
    ]

    operations = [
        migrations.RunPython(forwards, reverse_code=backwards),
    ]
