import pytest
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.models import ExhibitionProposal, ExhibitionProposalState, ExhibitorInfo
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


@pytest.mark.django_db
def test_apply_action_approve_creates_exhibitor(event):
    with scopes_disabled():
        proposal = _proposal(event, "approve@e.com")
        ProposalActionView().apply_action(proposal, "approve")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.approved_exhibitor_id is not None
        assert ExhibitorInfo.objects.filter(event=event, pk=proposal.approved_exhibitor_id).exists()


@pytest.mark.django_db
def test_apply_action_approve_sponsor_creates_sponsor(event):
    with scopes_disabled():
        proposal = _proposal(event, "sponsor@e.com", is_sponsor=True, is_exhibitor=False)
        ProposalActionView().apply_action(proposal, "approve")
        proposal.refresh_from_db()
        exhibitor = ExhibitorInfo.objects.get(pk=proposal.approved_exhibitor_id)
        assert exhibitor.is_sponsor is True
        assert exhibitor.is_exhibitor is False


@pytest.mark.django_db
def test_apply_action_reject_sets_state_without_partner(event):
    with scopes_disabled():
        proposal = _proposal(event, "reject@e.com")
        ProposalActionView().apply_action(proposal, "reject")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.REJECTED
        assert proposal.approved_exhibitor_id is None
        assert not ExhibitorInfo.objects.filter(event=event).exists()


@pytest.mark.django_db
def test_apply_action_withdraw_sets_state(event):
    with scopes_disabled():
        proposal = _proposal(event, "withdraw@e.com")
        ProposalActionView().apply_action(proposal, "withdraw")
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.WITHDRAWN


def test_build_message_reports_count_and_skips():
    view = ProposalActionView()
    message = view.build_message("approve", 2, 1)
    assert "2 proposals were approved." in message
    assert "1 was skipped" in message


def test_build_message_no_updates():
    view = ProposalActionView()
    assert str(view.build_message("reject", 0, 0)) == "No proposals were updated."
