from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.filters import EmailFilterForm
from exhibition.forms import ExhibitionEmailQueueForm
from exhibition.models import ExhibitionEmailQueue
from exhibition.views import EmailDeleteView, EmailEditView, EmailOutboxListView, EmailSentListView


def _member(event, email, **flags):
    user = User.objects.create_user(email=email, password="pw")
    team = event.organizer.teams.create(name=email, all_events=True, **flags)
    team.members.add(user)
    return user


def _view(view_class, event, user):
    request = RequestFactory().get("/")
    request.user = user
    request.event = event
    request.session = SimpleNamespace(session_key=None)
    view = view_class()
    view.request = request
    return view


def _email(event):
    return ExhibitionEmailQueue.objects.create(
        event=event, to_email="applicant@example.com", subject="Hello", body="<p>Body</p>"
    )


@pytest.mark.django_db
@pytest.mark.parametrize("view_class", [EmailEditView, EmailDeleteView, EmailOutboxListView, EmailSentListView])
def test_email_views_hide_recipients_for_hiding_reviewer(event, view_class):
    with scopes_disabled():
        user = _member(event, "r-hide@e.com", is_exhibition_reviewer=True, hide_exhibition_applicant_emails=True)
        assert _view(view_class, event, user).hide_applicant_emails is True


@pytest.mark.django_db
@pytest.mark.parametrize("view_class", [EmailEditView, EmailDeleteView, EmailOutboxListView, EmailSentListView])
def test_email_views_show_recipients_to_request_managers(event, view_class):
    with scopes_disabled():
        user = _member(event, "m@e.com", can_change_exhibition_proposals=True)
        assert _view(view_class, event, user).hide_applicant_emails is False


@pytest.mark.django_db
def test_edit_form_drops_recipient_when_hidden(event):
    with scopes_disabled():
        email = _email(event)
        form = ExhibitionEmailQueueForm(instance=email, event=event, hide_recipient=True)
        assert "to_email" not in form.fields


@pytest.mark.django_db
def test_edit_form_ignores_posted_recipient_when_hidden(event):
    with scopes_disabled():
        email = _email(event)
        form = ExhibitionEmailQueueForm(
            data={"to_email": "other@example.com", "subject": "Changed", "body": "<p>New</p>"},
            instance=email,
            event=event,
            hide_recipient=True,
        )
        assert form.is_valid(), form.errors
        form.save()
        email.refresh_from_db()
        assert email.to_email == "applicant@example.com"
        assert email.subject == "Changed"


@pytest.mark.django_db
def test_edit_form_keeps_recipient_for_managers(event):
    with scopes_disabled():
        email = _email(event)
        form = ExhibitionEmailQueueForm(instance=email, event=event)
        assert "to_email" in form.fields


@pytest.mark.django_db
def test_email_search_skips_recipient_when_hidden(event):
    with scopes_disabled():
        _email(event)
        queryset = ExhibitionEmailQueue.objects.filter(event=event)
        hidden = EmailFilterForm(data={"query": "applicant@"}, hide_emails=True)
        assert hidden.is_valid()
        assert not hidden.filter_qs(queryset).exists()
        shown = EmailFilterForm(data={"query": "applicant@"})
        assert shown.is_valid()
        assert shown.filter_qs(queryset).exists()


def test_email_sort_by_recipient_rejected_when_hidden():
    assert not EmailFilterForm(data={"ordering": "to_email"}, hide_emails=True).is_valid()
    assert not EmailFilterForm(data={"ordering": "-to_email"}, hide_emails=True).is_valid()
    assert EmailFilterForm(data={"ordering": "to_email"}).is_valid()
