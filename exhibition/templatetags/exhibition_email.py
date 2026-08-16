from django import template
from django.conf import settings

from ..models import ExhibitionEmailQueue

register = template.Library()


@register.simple_tag
def pending_email_count(event):
    """Number of unsent queued emails for the event, shown as a nav badge."""
    return ExhibitionEmailQueue.objects.filter(event=event, sent_at__isnull=True).count()


@register.filter
def locale_dir(locale):
    """``rtl`` for bidirectional locales, matching the i18n editor widgets."""
    return "rtl" if str(locale).split("-")[0] in settings.LANGUAGES_BIDI else "ltr"
