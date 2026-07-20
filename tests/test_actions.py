import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.models import (
    ExhibitionEmailQueue,
    ExhibitionProposal,
    ExhibitionProposalState,
    ExhibitorInfo,
)
from exhibition.views import ProposalActionView


def _proposal(event, email, state=ExhibitionProposalState.SUBMITTED, **kwargs):
    user = User.objects.create_user(email=email, password="pw")
    return ExhibitionProposal.objects.create(
        event=event,
        user=user,
        name=kwargs.pop("name", "Org"),
        state=state,
        **kwargs,
    )


def _action_view(event, email="organizer@e.com"):
    request = RequestFactory().post("/")
    request.user = User.objects.create_user(email=email, password="pw")
    request.event = event
    view = ProposalActionView()
    view.request = request
    return view


@pytest.mark.django_db
def test_apply_action_approve_creates_exhibitor(event):
    with scopes_disabled():
        proposal = _proposal(event, "approve@e.com")
        _action_view(event, "org-approve@e.com").apply_action(proposal, "approve")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.approved_exhibitor_id is not None
        assert ExhibitorInfo.objects.filter(event=event, pk=proposal.approved_exhibitor_id).exists()


@pytest.mark.django_db
def test_apply_action_approve_queues_acceptance_email(event):
    with scopes_disabled():
        proposal = _proposal(event, "approve-mail@e.com")
        _action_view(event, "org-approve-mail@e.com").apply_action(proposal, "approve")
        queued = ExhibitionEmailQueue.objects.filter(event=event, proposal=proposal)
        assert queued.count() == 1
        assert queued.first().to_email == "approve-mail@e.com"


@pytest.mark.django_db
def test_apply_action_approve_sponsor_creates_sponsor(event):
    with scopes_disabled():
        proposal = _proposal(event, "sponsor@e.com", is_sponsor=True, is_exhibitor=False)
        _action_view(event, "org-sponsor@e.com").apply_action(proposal, "approve")
        proposal.refresh_from_db()
        exhibitor = ExhibitorInfo.objects.get(pk=proposal.approved_exhibitor_id)
        assert exhibitor.is_sponsor is True
        assert exhibitor.is_exhibitor is False


@pytest.mark.django_db
def test_apply_action_reject_sets_state_without_partner(event):
    with scopes_disabled():
        proposal = _proposal(event, "reject@e.com")
        _action_view(event, "org-reject@e.com").apply_action(proposal, "reject")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.REJECTED
        assert proposal.approved_exhibitor_id is None
        assert not ExhibitorInfo.objects.filter(event=event).exists()


@pytest.mark.django_db
def test_apply_action_reject_queues_rejection_email(event):
    with scopes_disabled():
        proposal = _proposal(event, "reject-mail@e.com")
        _action_view(event, "org-reject-mail@e.com").apply_action(proposal, "reject")
        queued = ExhibitionEmailQueue.objects.filter(event=event, proposal=proposal)
        assert queued.count() == 1
        assert queued.first().to_email == "reject-mail@e.com"


@pytest.mark.django_db
def test_apply_action_withdraw_sets_state_without_email(event):
    with scopes_disabled():
        proposal = _proposal(event, "withdraw@e.com")
        _action_view(event, "org-withdraw@e.com").apply_action(proposal, "withdraw")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.WITHDRAWN
        assert not ExhibitionEmailQueue.objects.filter(event=event, proposal=proposal).exists()


def test_build_message_reports_count_and_skips():
    view = ProposalActionView()
    message = view.build_message("approve", 2, 1)
    assert "2 proposals were approved." in message
    assert "1 was skipped" in message


def test_build_message_no_updates():
    view = ProposalActionView()
    assert str(view.build_message("reject", 0, 0)) == "No proposals were updated."
