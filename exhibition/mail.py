"""Email helpers for the exhibition plugin."""

import logging
import re
from collections import defaultdict
from urllib.parse import urljoin

from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _lazy, gettext_noop
from i18nfield.strings import LazyI18nString

logger = logging.getLogger(__name__)

PROPOSAL_NEW = "proposal_new"
PROPOSAL_ACCEPTED = "proposal_accepted"
PROPOSAL_REJECTED = "proposal_rejected"

LIFECYCLE_ROLES = (PROPOSAL_NEW, PROPOSAL_ACCEPTED, PROPOSAL_REJECTED)

PLACEHOLDER_DOCS = (
    ("{event_name}", _lazy("The event's name")),
    ("{request_name}", _lazy("The request / organisation name")),
    ("{request_code}", _lazy("The request's unique code")),
    ("{request_url}", _lazy("Link for the applicant to view or edit the request")),
    ("{name}", _lazy("The applicant's name")),
)

_SETTINGS_PREFIX = "exhibition_mail_"


def subject_settings_key(role):
    return f"{_SETTINGS_PREFIX}{role}_subject"


def body_settings_key(role):
    return f"{_SETTINGS_PREFIX}{role}_body"


DEFAULT_TEMPLATES = {
    PROPOSAL_NEW: (
        LazyI18nString.from_gettext(gettext_noop("We received your request for {event_name}")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "thank you for submitting your request “{request_name}” to "
                "{event_name}. We have received it and will get back to you once it has "
                "been reviewed.\n\n"
                "You can review or edit your request here:\n{request_url}\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
    PROPOSAL_ACCEPTED: (
        LazyI18nString.from_gettext(gettext_noop("Your request for {event_name} has been accepted")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "we are happy to let you know that your request “{request_name}” "
                "for {event_name} has been accepted. We will be in touch with the next "
                "steps.\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
    PROPOSAL_REJECTED: (
        LazyI18nString.from_gettext(gettext_noop("Update on your request for {event_name}")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "thank you for your interest in {event_name}. Unfortunately we are unable "
                "to accept your request “{request_name}” this time.\n\n"
                "We hope to see you at a future event.\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
}


def get_email_template(event, role):
    """Return ``(subject, body)`` for a role, falling back to the defaults."""
    default_subject, default_body = DEFAULT_TEMPLATES[role]
    subject = event.settings.get(subject_settings_key(role), as_type=LazyI18nString) or default_subject
    body = event.settings.get(body_settings_key(role), as_type=LazyI18nString) or default_body
    return subject, body


class _SafeDict(dict):
    def __missing__(self, key):
        return "{" + key + "}"


_PREVIEW_URL_RE = re.compile(r"^(https?://|www\.)[^\s]+$")


def build_preview_placeholders(event):
    """Sample placeholder values for previews, wrapped like the tickets preview."""
    from django.utils.translation import gettext
    from eventyay.base.email import get_available_placeholders

    context = {}
    for placeholder in get_available_placeholders(event, ["event", "proposal", "exhibitor"]).values():
        sample = str(placeholder.render_sample(event)).strip()
        if _PREVIEW_URL_RE.match(sample):
            context[placeholder.identifier] = (
                f'<a href="{sample}" target="_blank" rel="noopener noreferrer">{sample}</a>'
            )
        else:
            context[placeholder.identifier] = '<span class="placeholder" title="{}">{}</span>'.format(
                gettext("This value will be replaced based on dynamic parameters."),
                sample,
            )
    return _SafeDict(context)


def recipient_locale(event, user=None):
    locale = getattr(user, "locale", None) if user else None
    return locale or event.settings.locale


def _render(text, context, locale):
    """Localise ``text`` and substitute ``{placeholder}`` values."""
    localized = str(LazyI18nString(text).localize(locale)) if locale else str(text)
    try:
        return localized.format_map(defaultdict(str, context))
    except (ValueError, IndexError):
        logger.warning("Could not render exhibition email template: %r", localized)
        return localized


def build_proposal_context(event, proposal):
    from eventyay.base.email import get_email_context

    context = get_email_context(event=event, proposal=proposal)
    context.setdefault("event_name", str(event.name))
    return context


def build_exhibitor_context(event, exhibitor):
    from eventyay.base.email import get_email_context

    context = get_email_context(event=event, exhibitor=exhibitor)
    context.setdefault("event_name", str(event.name))
    return context


def proposal_public_url(proposal):
    path = reverse(
        "plugins:exhibition:proposal.user_edit",
        kwargs={
            "organizer": proposal.event.organizer.slug,
            "event": proposal.event.slug,
            "code": proposal.code,
        },
    )
    return urljoin(django_settings.SITE_URL, path)


def queue_proposal_email(event, proposal, role, *, send_now=False, requestor=None):
    """Queue a lifecycle email; ``send_now`` sends it instead of leaving it in the outbox."""
    from .models import ExhibitionEmailQueue

    to_email = (proposal.email or "").strip() or (proposal.user.email if proposal.user_id else "")
    if not to_email:
        return None

    user = proposal.user if proposal.user_id else None
    locale = recipient_locale(event, user)
    subject_tpl, body_tpl = get_email_template(event, role)
    context = build_proposal_context(event, proposal)

    queued = ExhibitionEmailQueue.objects.create(
        event=event,
        proposal=proposal,
        to_email=to_email,
        subject=_render(subject_tpl, context, locale),
        body=_render(body_tpl, context, locale),
        locale=locale or "",
    )
    if send_now:
        queued.send(requestor=requestor)
    return queued


def queue_exhibitor_access_email(event, exhibitor, *, requestor=None):
    """Queue the access-credentials email; ``None`` if no recipient or template."""
    from .models import ExhibitionEmailQueue, ExhibitorSettings

    to_email = (exhibitor.email or "").strip()
    if not to_email:
        return None

    exhibitor_settings = ExhibitorSettings.objects.filter(event=event).first()
    subject_tpl = (exhibitor_settings.exhibitors_access_mail_subject if exhibitor_settings else "") or ""
    body_tpl = (exhibitor_settings.exhibitors_access_mail_body if exhibitor_settings else "") or ""
    if not subject_tpl and not body_tpl:
        return None

    locale = recipient_locale(event)
    context = build_exhibitor_context(event, exhibitor)

    return ExhibitionEmailQueue.objects.create(
        event=event,
        exhibitor=exhibitor,
        to_email=to_email,
        subject=_render(subject_tpl, context, locale),
        body=_render(body_tpl, context, locale),
        locale=locale or "",
    )
