import logging

from django.utils.timezone import now
from eventyay.base.models import Event
from eventyay.base.services.tasks import ProfiledEventTask
from eventyay.celery_app import app

logger = logging.getLogger(__name__)


@app.task(base=ProfiledEventTask, bind=True, max_retries=5, default_retry_delay=60, acks_late=True)
def send_scheduled_email(self, event_id, queue_id):
    from .models import ExhibitionEmailQueue

    if isinstance(event_id, Event):
        event = event_id
        original_event_id = event.pk
    else:
        original_event_id = event_id
        try:
            event = Event.objects.get(pk=event_id)
        except Event.DoesNotExist:
            logger.error("[Exhibition] Event %s not found for queued email %s", event_id, queue_id)
            return

    queued = ExhibitionEmailQueue.objects.filter(pk=queue_id, event=event, sent_at__isnull=True).first()
    if queued is None:
        return

    if queued.scheduled_at and queued.scheduled_at > now():
        countdown = max(1, int((queued.scheduled_at - now()).total_seconds()))
        self.retry(countdown=countdown, args=[original_event_id, queue_id], throw=False)
        return

    queued.send()
