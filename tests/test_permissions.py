from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.forms import ExhibitionProposalReviewForm, ExhibitionProposalReviewNotesForm
from exhibition.models import ExhibitionProposal, ExhibitionProposalState
from exhibition.utils import should_hide_applicant_emails
from exhibition.views import ProposalDetailView


def _proposal(event, email, state=ExhibitionProposalState.SUBMITTED):
    submitter = User.objects.create_user(email=email, password="pw")
    return ExhibitionProposal.objects.create(event=event, user=submitter, name="Org", state=state)


def _member(event, email, **flags):
    user = User.objects.create_user(email=email, password="pw")
    team = event.organizer.teams.create(name=email, all_events=True, **flags)
    team.members.add(user)
    return user


def _detail_view(event, user):
    request = RequestFactory().get("/")
    request.user = user
    request.event = event
    request.session = SimpleNamespace(session_key=None)
    view = ProposalDetailView()
    view.request = request
    return view


@pytest.mark.django_db
def test_hide_emails_for_reviewer_with_flag(event):
    with scopes_disabled():
        user = _member(event, "r-hide@e.com", is_exhibition_reviewer=True, hide_exhibition_applicant_emails=True)
        assert should_hide_applicant_emails(user, event) is True


@pytest.mark.django_db
def test_no_hide_for_reviewer_without_flag(event):
    with scopes_disabled():
        user = _member(event, "r-plain@e.com", is_exhibition_reviewer=True)
        assert should_hide_applicant_emails(user, event) is False


@pytest.mark.django_db
def test_no_hide_for_proposal_manager_even_with_flag(event):
    with scopes_disabled():
        user = _member(
            event,
            "m-hide@e.com",
            can_change_exhibition_proposals=True,
            is_exhibition_reviewer=True,
            hide_exhibition_applicant_emails=True,
        )
        assert should_hide_applicant_emails(user, event) is False


@pytest.mark.django_db
def test_no_hide_without_exhibition_team(event):
    with scopes_disabled():
        user = _member(event, "orders@e.com", can_view_orders=True)
        assert should_hide_applicant_emails(user, event) is False


@pytest.mark.django_db
def test_reviewer_gets_notes_only_form(event):
    with scopes_disabled():
        user = _member(event, "rv-form@e.com", is_exhibition_reviewer=True)
        view = _detail_view(event, user)
        assert view.can_manage() is False
        assert view.get_form_class() is ExhibitionProposalReviewNotesForm


@pytest.mark.django_db
def test_manager_gets_full_review_form(event):
    with scopes_disabled():
        user = _member(event, "mg-form@e.com", can_change_exhibition_proposals=True)
        proposal = _proposal(event, "sub-form@e.com", state=ExhibitionProposalState.SUBMITTED)
        view = _detail_view(event, user)
        view.object = proposal
        assert view.can_manage() is True
        assert view.can_review() is True
        assert view.get_form_class() is ExhibitionProposalReviewForm


@pytest.mark.django_db
def test_manager_gets_notes_form_for_draft_proposal(event):
    with scopes_disabled():
        user = _member(event, "mg-draft@e.com", can_change_exhibition_proposals=True)
        proposal = _proposal(event, "sub-draft@e.com", state=ExhibitionProposalState.DRAFT)
        view = _detail_view(event, user)
        view.object = proposal
        assert view.can_manage() is True
        assert view.can_review() is False
        assert view.get_form_class() is ExhibitionProposalReviewNotesForm


@pytest.mark.django_db
def test_manager_gets_notes_form_for_rejected_proposal(event):
    with scopes_disabled():
        user = _member(event, "mg-rejected@e.com", can_change_exhibition_proposals=True)
        proposal = _proposal(event, "sub-rejected@e.com", state=ExhibitionProposalState.REJECTED)
        view = _detail_view(event, user)
        view.object = proposal
        assert view.can_manage() is True
        assert view.can_review() is False
        assert view.get_form_class() is ExhibitionProposalReviewNotesForm


@pytest.mark.django_db
def test_manager_gets_notes_form_for_accepted_proposal(event):
    with scopes_disabled():
        user = _member(event, "mg-accepted@e.com", can_change_exhibition_proposals=True)
        proposal = _proposal(event, "sub-accepted@e.com", state=ExhibitionProposalState.ACCEPTED)
        view = _detail_view(event, user)
        view.object = proposal
        assert view.can_manage() is True
        assert view.can_review() is False
        assert view.get_form_class() is ExhibitionProposalReviewNotesForm
