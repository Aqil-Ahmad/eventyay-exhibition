import json
from datetime import timedelta
from unittest.mock import patch

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.test import RequestFactory
from django.utils import timezone
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition import mail as mail_helpers
from exhibition.forms import ExhibitionComposeForm, ExhibitionMailTemplatesForm
from exhibition.models import (
    ExhibitionEmailQueue,
    ExhibitionProposal,
    ExhibitionProposalState,
    ExhibitorInfo,
    ExhibitorSettings,
    SponsorGroup,
)
from exhibition.views import EmailComposeView, EmailTemplatePreviewView


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


def _proposal(event, name, state, *, email="", user=None, is_exhibitor=True, is_sponsor=False, sponsor_group=None):
    if user is None:
        user = User.objects.create_user(email=f"{name.lower().replace(' ', '')}-user@example.com", password="pw")
    with scopes_disabled():
        return ExhibitionProposal.objects.create(
            event=event,
            user=user,
            name=name,
            state=state,
            email=email,
            is_exhibitor=is_exhibitor,
            is_sponsor=is_sponsor,
            sponsor_group=sponsor_group,
        )


@pytest.mark.django_db
def test_compose_recipients_filters_by_state(mail_event):
    accepted = _proposal(mail_event, "A", ExhibitionProposalState.ACCEPTED, email="a@example.com")
    _proposal(mail_event, "R", ExhibitionProposalState.REJECTED, email="r@example.com")
    _proposal(mail_event, "D", ExhibitionProposalState.DRAFT, email="d@example.com")

    with scopes_disabled():
        result = list(mail_helpers.compose_recipients(mail_event, states=[ExhibitionProposalState.ACCEPTED]))

    assert result == [accepted]


@pytest.mark.django_db
def test_compose_recipients_excludes_drafts_when_no_state_filter(mail_event):
    _proposal(mail_event, "D", ExhibitionProposalState.DRAFT, email="d@example.com")
    submitted = _proposal(mail_event, "S", ExhibitionProposalState.SUBMITTED, email="s@example.com")

    with scopes_disabled():
        result = list(mail_helpers.compose_recipients(mail_event))

    assert result == [submitted]


@pytest.mark.django_db
def test_compose_recipients_filters_by_type_and_group(mail_event):
    with scopes_disabled():
        group = SponsorGroup.objects.create(event=mail_event, name="Gold")
    sponsor = _proposal(
        mail_event,
        "Sp",
        ExhibitionProposalState.ACCEPTED,
        email="sp@example.com",
        is_exhibitor=False,
        is_sponsor=True,
        sponsor_group=group,
    )
    _proposal(mail_event, "Ex", ExhibitionProposalState.ACCEPTED, email="ex@example.com")

    with scopes_disabled():
        by_type = list(mail_helpers.compose_recipients(mail_event, partner_type="sponsor"))
        by_group = list(mail_helpers.compose_recipients(mail_event, sponsor_group=group))

    assert by_type == [sponsor]
    assert by_group == [sponsor]


@pytest.mark.django_db
def test_queue_compose_emails_fans_out_and_dedupes(mail_event):
    _proposal(mail_event, "One", ExhibitionProposalState.ACCEPTED, email="one@example.com")
    _proposal(mail_event, "Two", ExhibitionProposalState.ACCEPTED, email="two@example.com")
    _proposal(mail_event, "Dup", ExhibitionProposalState.ACCEPTED, email="One@Example.com")

    with scopes_disabled():
        recipients = list(mail_helpers.compose_recipients(mail_event))
        created = mail_helpers.queue_compose_emails(mail_event, recipients, "Hi", "Body")
        emails = {row.to_email for row in ExhibitionEmailQueue.objects.filter(event=mail_event)}

    assert len(created) == 2
    assert {email.lower() for email in emails} == {"one@example.com", "two@example.com"}
    assert all(row.sent_at is None for row in created)


@pytest.mark.django_db
def test_queue_compose_emails_resolves_placeholders(mail_event):
    proposal = _proposal(mail_event, "Acme Corp", ExhibitionProposalState.ACCEPTED, email="a@example.com")

    with scopes_disabled():
        created = mail_helpers.queue_compose_emails(
            mail_event, [proposal], "For {request_name}", "Hello from {event_name}"
        )

    assert created[0].subject == "For Acme Corp"
    assert str(mail_event.name) in created[0].body


@pytest.mark.django_db
def test_queue_compose_emails_send_now(mail_event):
    proposal = _proposal(mail_event, "Acme", ExhibitionProposalState.ACCEPTED, email="a@example.com")

    with patch("eventyay.base.services.mail.mail") as mocked_mail:
        with scopes_disabled():
            created = mail_helpers.queue_compose_emails(mail_event, [proposal], "S", "B", send_now=True)

    assert created[0].sent_at is not None
    assert mocked_mail.call_count == 1


@pytest.mark.django_db
def test_compose_form_requires_subject_and_body(mail_event):
    form = ExhibitionComposeForm(data={"states": [ExhibitionProposalState.ACCEPTED]}, event=mail_event)
    assert not form.is_valid()
    assert "subject" in form.errors
    assert "body" in form.errors


@pytest.mark.django_db
def test_compose_view_saves_to_outbox(mail_event):
    _proposal(mail_event, "Acme", ExhibitionProposalState.ACCEPTED, email="a@example.com")
    form = ExhibitionComposeForm(
        data={
            "states": [ExhibitionProposalState.ACCEPTED],
            "partner_type": "",
            "subject": "Hi",
            "body": "Body",
        },
        event=mail_event,
    )
    assert form.is_valid(), form.errors

    request = RequestFactory().post("/compose", data={})
    request.event = mail_event
    request.user = None
    request.session = {}
    request._messages = FallbackStorage(request)
    view = EmailComposeView()
    view.request = request
    response = view.form_valid(form)

    assert response.status_code == 302
    with scopes_disabled():
        assert ExhibitionEmailQueue.objects.filter(event=mail_event, sent_at__isnull=True).count() == 1


@pytest.mark.django_db
def test_queue_compose_emails_stores_scheduled_at(mail_event):
    proposal = _proposal(mail_event, "Acme", ExhibitionProposalState.ACCEPTED, email="a@example.com")
    when = timezone.now() + timedelta(days=1)

    with scopes_disabled():
        created = mail_helpers.queue_compose_emails(mail_event, [proposal], "S", "B", scheduled_at=when)

    assert created[0].scheduled_at == when
    assert created[0].sent_at is None


@pytest.mark.django_db
def test_compose_form_rejects_past_scheduled_at(mail_event):
    form = ExhibitionComposeForm(
        data={
            "states": [ExhibitionProposalState.ACCEPTED],
            "subject": "Hi",
            "body": "Body",
            "scheduled_at": (timezone.now() - timedelta(hours=1)).strftime("%Y-%m-%dT%H:%M"),
        },
        event=mail_event,
    )
    assert not form.is_valid()
    assert "scheduled_at" in form.errors


@pytest.mark.django_db
def test_compose_view_schedules_emails(mail_event):
    _proposal(mail_event, "Acme", ExhibitionProposalState.ACCEPTED, email="a@example.com")
    when = timezone.now() + timedelta(days=1)
    form = ExhibitionComposeForm(
        data={
            "states": [ExhibitionProposalState.ACCEPTED],
            "partner_type": "",
            "subject": "Hi",
            "body": "Body",
            "scheduled_at": when.strftime("%Y-%m-%dT%H:%M"),
        },
        event=mail_event,
    )
    assert form.is_valid(), form.errors

    request = RequestFactory().post("/compose", data={"_send": "1"})
    request.event = mail_event
    request.user = None
    request.session = {}
    request._messages = FallbackStorage(request)
    view = EmailComposeView()
    view.request = request

    with patch("exhibition.tasks.send_scheduled_email.apply_async") as mocked_apply:
        response = view.form_valid(form)

    assert response.status_code == 302
    assert mocked_apply.call_count == 1
    with scopes_disabled():
        row = ExhibitionEmailQueue.objects.get(event=mail_event)
    assert row.scheduled_at is not None
    assert row.sent_at is None


@pytest.mark.django_db
def test_scheduled_task_sends_when_due(mail_event, proposal):
    from exhibition.tasks import send_scheduled_email

    with scopes_disabled():
        queued = ExhibitionEmailQueue.objects.create(
            event=mail_event,
            proposal=proposal,
            to_email="a@example.com",
            subject="S",
            body="B",
            scheduled_at=timezone.now() - timedelta(minutes=1),
        )

    with patch("eventyay.base.services.mail.mail") as mocked_mail:
        send_scheduled_email.run(mail_event.pk, queued.pk)

    with scopes_disabled():
        queued.refresh_from_db()
    assert queued.sent_at is not None
    assert queued.scheduled_at is None
    assert mocked_mail.call_count == 1
