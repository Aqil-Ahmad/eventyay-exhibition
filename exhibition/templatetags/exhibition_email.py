from django import template

from ..models import ExhibitionEmailQueue

register = template.Library()


@register.simple_tag
def pending_email_count(event):
    """Number of unsent queued emails for the event, shown as a nav badge."""
    return ExhibitionEmailQueue.objects.filter(event=event, sent_at__isnull=True).count()
