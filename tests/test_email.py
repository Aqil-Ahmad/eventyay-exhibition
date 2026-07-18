import json
from unittest.mock import patch

import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition import mail as mail_helpers
from exhibition.forms import ExhibitionMailTemplatesForm
from exhibition.models import (
    ExhibitionEmailQueue,
    ExhibitionProposal,
    ExhibitionProposalState,
    ExhibitorInfo,
    ExhibitorSettings,
)
from exhibition.views import EmailTemplatePreviewView


def _locale_index(event, field_name, locale):
    """Index of an i18n sub-input, positioned by ``widget.locales``."""
    widget = ExhibitionMailTemplatesForm(obj=event).fields[field_name].widget
    return widget.locales.index(locale)


@pytest.fixture
def mail_event(event):
    """Event with the plugin enabled, so the placeholder signal is dispatched."""
    event.plugins = "exhibition"
    event.save(update_fields=["plugins"])
    return event


@pytest.fixture
def applicant(db):
    return User.objects.create_user(email="applicant@example.com", password="pw", fullname="Jane Applicant")


@pytest.fixture
def proposal(mail_event, applicant):
    with scopes_disabled():
        return ExhibitionProposal.objects.create(
            event=mail_event,
            user=applicant,
            name="Acme Corp",
            state=ExhibitionProposalState.SUBMITTED,
        )


@pytest.fixture
def exhibitor(mail_event):
    with scopes_disabled():
        return ExhibitorInfo.objects.create(
            event=mail_event,
            name="Acme Corp",
            email="exhibitor@example.com",
            booth_id="B-9",
        )


@pytest.mark.django_db
def test_get_email_template_falls_back_to_defaults(mail_event):
    subject, body = mail_helpers.get_email_template(mail_event, mail_helpers.PROPOSAL_NEW)
    assert "{event_name}" in str(subject)
    assert "{request_name}" in str(body)


@pytest.mark.django_db
def test_get_email_template_uses_saved_override(mail_event):
    mail_event.settings.set(mail_helpers.subject_settings_key(mail_helpers.PROPOSAL_NEW), "Custom subject")
    subject, _body = mail_helpers.get_email_template(mail_event, mail_helpers.PROPOSAL_NEW)
    assert str(subject) == "Custom subject"


@pytest.mark.django_db
def test_templates_form_saves_to_event_settings(mail_event):
    subject_key = mail_helpers.subject_settings_key(mail_helpers.PROPOSAL_NEW)
    body_key = mail_helpers.body_settings_key(mail_helpers.PROPOSAL_NEW)
    form = ExhibitionMailTemplatesForm(
        data={
            f"{subject_key}_{_locale_index(mail_event, subject_key, 'en')}": "Saved subject",
            f"{body_key}_{_locale_index(mail_event, body_key, 'en')}": "Saved body",
        },
        obj=mail_event,
    )
    assert form.is_valid(), form.errors
    form.save()

    subject, body = mail_helpers.get_email_template(mail_event, mail_helpers.PROPOSAL_NEW)
    assert str(subject) == "Saved subject"
    assert str(body) == "Saved body"


@pytest.mark.django_db
def test_queue_proposal_email_resolves_placeholders(mail_event, proposal):
    queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_NEW)

    assert queued is not None
    assert queued.to_email == "applicant@example.com"
    assert "{request_name}" not in queued.body
    assert "{event_name}" not in queued.subject
    assert "Acme Corp" in queued.body
    assert str(mail_event.name) in queued.subject


@pytest.mark.django_db
def test_queue_proposal_email_is_unsent_by_default(mail_event, proposal):
    queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_ACCEPTED)
    assert queued.sent_at is None


@pytest.mark.django_db
def test_queue_proposal_email_send_now_sends_immediately(mail_event, proposal):
    with patch("eventyay.base.services.mail.mail") as mocked_mail:
        queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_NEW, send_now=True)

    assert queued.sent_at is not None
    assert mocked_mail.call_count == 1
    assert mocked_mail.call_args.kwargs["email"] == "applicant@example.com"


@pytest.mark.django_db
def test_queue_proposal_email_prefers_proposal_email_over_user_email(mail_event, proposal):
    proposal.email = "contact@example.com"
    with scopes_disabled():
        proposal.save(update_fields=["email"])

    queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_REJECTED)
    assert queued.to_email == "contact@example.com"


@pytest.mark.django_db
def test_queue_proposal_email_returns_none_without_recipient(mail_event, applicant, proposal):
    applicant.email = ""
    applicant.save(update_fields=["email"])
    proposal.user.refresh_from_db()

    assert mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_NEW) is None


@pytest.mark.django_db
def test_send_marks_sent_and_calls_core_mail(mail_event, proposal):
    queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_ACCEPTED)

    with patch("eventyay.base.services.mail.mail") as mocked_mail:
        queued.send()

    assert queued.sent_at is not None
    kwargs = mocked_mail.call_args.kwargs
    assert kwargs["email"] == queued.to_email
    assert kwargs["subject"] == queued.subject
    assert kwargs["event"] == mail_event


@pytest.mark.django_db
def test_send_twice_is_a_noop(mail_event, proposal):
    queued = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_ACCEPTED)

    with patch("eventyay.base.services.mail.mail") as mocked_mail:
        queued.send()
        first_sent_at = queued.sent_at
        queued.send()

    assert mocked_mail.call_count == 1
    assert queued.sent_at == first_sent_at


@pytest.mark.django_db
def test_outbox_and_sent_querysets_do_not_overlap(mail_event, proposal):
    unsent = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_ACCEPTED)
    sent = mail_helpers.queue_proposal_email(mail_event, proposal, mail_helpers.PROPOSAL_REJECTED)
    with patch("eventyay.base.services.mail.mail"):
        sent.send()

    with scopes_disabled():
        outbox = ExhibitionEmailQueue.objects.filter(event=mail_event, sent_at__isnull=True)
        sent_list = ExhibitionEmailQueue.objects.filter(event=mail_event, sent_at__isnull=False)

    assert list(outbox) == [unsent]
    assert list(sent_list) == [sent]


@pytest.mark.django_db
def test_access_email_resolves_placeholders_and_keeps_newlines(mail_event, exhibitor):
    with scopes_disabled():
        ExhibitorSettings.objects.create(
            event=mail_event,
            exhibitors_access_mail_subject="Access for {event_name}",
            exhibitors_access_mail_body="Hello {exhibitor_name},\n\nBooth: {booth_id}\nCode: {exhibitor_access_code}",
        )

    queued = mail_helpers.queue_exhibitor_access_email(mail_event, exhibitor)

    assert queued is not None
    assert queued.sent_at is None
    assert queued.to_email == "exhibitor@example.com"
    assert "Acme Corp" in queued.body
    assert "B-9" in queued.body
    assert exhibitor.key in queued.body
    assert "\n" in queued.body


@pytest.mark.django_db
def test_access_email_returns_none_without_template(mail_event, exhibitor):
    with scopes_disabled():
        ExhibitorSettings.objects.create(
            event=mail_event,
            exhibitors_access_mail_subject="",
            exhibitors_access_mail_body="",
        )

    assert mail_helpers.queue_exhibitor_access_email(mail_event, exhibitor) is None


@pytest.mark.django_db
def test_access_email_returns_none_without_exhibitor_email(mail_event):
    with scopes_disabled():
        ExhibitorSettings.objects.create(
            event=mail_event,
            exhibitors_access_mail_subject="Access",
            exhibitors_access_mail_body="Code: {exhibitor_access_code}",
        )
        exhibitor = ExhibitorInfo.objects.create(event=mail_event, name="No Email Co", email="")

    assert mail_helpers.queue_exhibitor_access_email(mail_event, exhibitor) is None


def _preview(event, role, body_by_locale):
    """POST draft body text to the preview endpoint."""
    field_name = mail_helpers.body_settings_key(role)
    data = {"role": role}
    for locale, text in body_by_locale.items():
        data[f"{field_name}_{_locale_index(event, field_name, locale)}"] = text
    request = RequestFactory().post("/preview", data=data)
    request.event = event
    return EmailTemplatePreviewView().post(request)


@pytest.mark.django_db
def test_preview_renders_markdown_and_highlights_placeholders(mail_event):
    mail_event.settings.locales = ["en"]
    response = _preview(mail_event, mail_helpers.PROPOSAL_NEW, {"en": "Hi {request_name}"})

    assert response.status_code == 200
    previews = json.loads(response.content)["previews"]
    assert "<p>" in previews["en"]
    assert 'class="placeholder"' in previews["en"]
    assert "{request_name}" not in previews["en"]


@pytest.mark.django_db
def test_preview_renders_each_active_locale(mail_event):
    mail_event.settings.locales = ["en", "de"]
    response = _preview(
        mail_event,
        mail_helpers.PROPOSAL_ACCEPTED,
        {"en": "Hello", "de": "Hallo"},
    )

    previews = json.loads(response.content)["previews"]
    assert set(previews.keys()) == {"en", "de"}
    assert "Hello" in previews["en"]
    assert "Hallo" in previews["de"]


@pytest.mark.django_db
def test_preview_sanitises_html(mail_event):
    mail_event.settings.locales = ["en"]
    response = _preview(mail_event, mail_helpers.PROPOSAL_NEW, {"en": "<script>alert(1)</script>"})

    previews = json.loads(response.content)["previews"]
    assert "<script>" not in previews["en"]


@pytest.mark.django_db
def test_preview_rejects_unknown_role(mail_event):
    request = RequestFactory().post("/preview", data={"role": "not_a_role"})
    request.event = mail_event
    response = EmailTemplatePreviewView().post(request)

    assert response.status_code == 400
