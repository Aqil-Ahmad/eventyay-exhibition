"""Email helpers for the exhibition plugin.

The plugin reuses the core email stack (``eventyay.base.services.mail.mail`` for
sending and ``eventyay.base.email.get_email_context`` /
``register_mail_placeholders`` for placeholders) and only owns a thin
per-recipient queue (:class:`~exhibition.models.ExhibitionEmailQueue`) plus the
editable templates stored in ``event.settings``.

Placeholders are rendered into the queued email at *queue* time, for the
recipient's locale, so the outbox shows the final text an organiser can edit
before sending.
"""

from collections import defaultdict
from urllib.parse import urljoin

from django.conf import settings as django_settings
from django.urls import reverse
from django.utils.translation import gettext_lazy as _lazy, gettext_noop
from i18nfield.strings import LazyI18nString

# Lifecycle template roles. These double as the ``event.settings`` key stems:
# e.g. PROPOSAL_NEW -> exhibition_mail_proposal_new_subject / _body.
PROPOSAL_NEW = "proposal_new"
PROPOSAL_ACCEPTED = "proposal_accepted"
PROPOSAL_REJECTED = "proposal_rejected"

LIFECYCLE_ROLES = (PROPOSAL_NEW, PROPOSAL_ACCEPTED, PROPOSAL_REJECTED)

# Placeholders documented in the settings UI. Descriptions are lazy-translated.
PLACEHOLDER_DOCS = (
    ("{event_name}", _lazy("The event's name")),
    ("{proposal_name}", _lazy("The proposal / organisation name")),
    ("{proposal_code}", _lazy("The proposal's unique code")),
    ("{proposal_url}", _lazy("Link for the applicant to view or edit the proposal")),
    ("{name}", _lazy("The applicant's name")),
)

_SETTINGS_PREFIX = "exhibition_mail_"


def subject_settings_key(role):
    return f"{_SETTINGS_PREFIX}{role}_subject"


def body_settings_key(role):
    return f"{_SETTINGS_PREFIX}{role}_body"


# Default templates. gettext_noop keeps them translatable without evaluating at
# import time; wrapped in LazyI18nString so the settings store round-trips them.
DEFAULT_TEMPLATES = {
    PROPOSAL_NEW: (
        LazyI18nString.from_gettext(gettext_noop("We received your proposal for {event_name}")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "thank you for submitting your proposal “{proposal_name}” to "
                "{event_name}. We have received it and will get back to you once it has "
                "been reviewed.\n\n"
                "You can review or edit your proposal here:\n{proposal_url}\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
    PROPOSAL_ACCEPTED: (
        LazyI18nString.from_gettext(gettext_noop("Your proposal for {event_name} has been accepted")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "we are happy to let you know that your proposal “{proposal_name}” "
                "for {event_name} has been accepted. We will be in touch with the next "
                "steps.\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
    PROPOSAL_REJECTED: (
        LazyI18nString.from_gettext(gettext_noop("Update on your proposal for {event_name}")),
        LazyI18nString.from_gettext(
            gettext_noop(
                "Hello,\n\n"
                "thank you for your interest in {event_name}. Unfortunately we are unable "
                "to accept your proposal “{proposal_name}” this time.\n\n"
                "We hope to see you at a future event.\n\n"
                "Best regards,\n"
                "The {event_name} team"
            )
        ),
    ),
}


def get_email_template(event, role):
    """Return ``(subject, body)`` as LazyI18nStrings for a lifecycle role.

    Falls back to the built-in defaults when the organiser has not customised
    the template in the settings store.
    """
    default_subject, default_body = DEFAULT_TEMPLATES[role]
    subject = event.settings.get(subject_settings_key(role), as_type=LazyI18nString) or default_subject
    body = event.settings.get(body_settings_key(role), as_type=LazyI18nString) or default_body
    return subject, body


def recipient_locale(event, user=None):
    locale = getattr(user, "locale", None) if user else None
    return locale or event.settings.locale


def _render(text, context, locale):
    """Localise ``text`` and substitute ``{placeholder}`` values."""
    localized = str(LazyI18nString(text).localize(locale)) if locale else str(text)
    return localized.format_map(defaultdict(str, context))


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
    """Create an ExhibitionEmailQueue row for a proposal lifecycle email.

    :param send_now: send immediately (used for the submission confirmation);
        otherwise the row stays unsent in the outbox for organiser review.
    """
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
    """Queue the access-credentials email for an exhibitor.

    Uses the existing ``ExhibitorSettings.exhibitors_access_mail_subject/body``
    fields as the template. Returns ``None`` if the exhibitor has no email.
    """
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
