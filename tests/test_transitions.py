import pytest
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.models import (
    ExhibitionEmailQueue,
    ExhibitionProposal,
    ExhibitionProposalState,
    ExhibitorInfo,
)
from exhibition.utils import create_exhibitor_from_proposal


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
@pytest.mark.parametrize(
    "state,expected",
    [
        (ExhibitionProposalState.DRAFT, {"submitted"}),
        (ExhibitionProposalState.SUBMITTED, {"accepted", "rejected", "withdrawn"}),
        (ExhibitionProposalState.ACCEPTED, {"submitted", "rejected", "withdrawn"}),
        (ExhibitionProposalState.REJECTED, {"submitted", "accepted"}),
        (ExhibitionProposalState.WITHDRAWN, {"submitted"}),
    ],
)
def test_transition_matrix(event, state, expected):
    with scopes_disabled():
        proposal = _proposal(event, f"{state}@e.com", state=state)
        candidates = (
            ExhibitionProposalState.SUBMITTED,
            ExhibitionProposalState.ACCEPTED,
            ExhibitionProposalState.REJECTED,
            ExhibitionProposalState.WITHDRAWN,
        )
        allowed = {target.value for target in candidates if proposal.can_transition_to(target)}
        assert allowed == expected


@pytest.mark.django_db
def test_available_review_actions_for_rejected_includes_approve(event):
    with scopes_disabled():
        proposal = _proposal(event, "rej@e.com", state=ExhibitionProposalState.REJECTED)
        assert set(proposal.available_review_actions()) == {"approve", "reopen"}


@pytest.mark.django_db
def test_available_review_actions_for_accepted_has_no_approve(event):
    with scopes_disabled():
        proposal = _proposal(event, "acc@e.com", state=ExhibitionProposalState.ACCEPTED)
        assert set(proposal.available_review_actions()) == {"reject", "withdraw", "reopen"}


@pytest.mark.django_db
def test_create_exhibitor_from_proposal_captures_profile_snapshot(event):
    with scopes_disabled():
        proposal = _proposal(event, "snap@e.com", description="Original description")
        create_exhibitor_from_proposal(proposal)
        proposal.refresh_from_db()

        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.profile_edited_at is None
        assert proposal.accepted_profile_snapshot == proposal.submitter_profile_values()
        assert proposal.accepted_profile_snapshot["description"] == "Original description"


@pytest.mark.django_db
def test_reapprove_after_reject_refreshes_profile_snapshot_and_clears_edited_flag(event):
    with scopes_disabled():
        proposal = _proposal(event, "refresh@e.com", description="Original description")
        create_exhibitor_from_proposal(proposal)
        proposal.refresh_from_db()

        proposal.description = "Edited after acceptance"
        proposal.profile_edited_at = proposal.updated
        proposal.save(update_fields=["description", "profile_edited_at"])

        proposal.reject()
        proposal.refresh_from_db()
        proposal.approve()
        proposal.refresh_from_db()

        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.profile_edited_at is None
        assert proposal.accepted_profile_snapshot["description"] == "Edited after acceptance"
        assert proposal.profile_field_changes() == []


@pytest.mark.django_db
def test_reject_after_accept_deactivates_partner(event):
    with scopes_disabled():
        proposal = _proposal(event, "flip@e.com")
        exhibitor = create_exhibitor_from_proposal(proposal)
        assert exhibitor.active is True

        proposal.refresh_from_db()
        proposal.reject()
        exhibitor.refresh_from_db()
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.REJECTED
        assert exhibitor.active is False
        assert ExhibitorInfo.objects.filter(pk=exhibitor.pk).exists()


@pytest.mark.django_db
def test_reapprove_after_reject_reactivates_same_partner(event):
    with scopes_disabled():
        proposal = _proposal(event, "cycle@e.com")
        exhibitor = create_exhibitor_from_proposal(proposal)
        proposal.refresh_from_db()

        proposal.reject()
        exhibitor.refresh_from_db()
        assert exhibitor.active is False

        proposal.refresh_from_db()
        reapproved = proposal.approve()
        exhibitor.refresh_from_db()
        proposal.refresh_from_db()
        assert reapproved.pk == exhibitor.pk
        assert exhibitor.active is True
        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.approved_exhibitor_id == exhibitor.pk
        assert ExhibitorInfo.objects.filter(event=event).count() == 1


@pytest.mark.django_db
def test_reopen_moves_accepted_back_to_submitted_and_hides_partner(event):
    with scopes_disabled():
        proposal = _proposal(event, "reopen@e.com")
        exhibitor = create_exhibitor_from_proposal(proposal)
        proposal.refresh_from_db()

        proposal.reopen()
        proposal.refresh_from_db()
        exhibitor.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.SUBMITTED
        assert exhibitor.active is False


@pytest.mark.django_db
def test_reopen_sends_no_decision_email(event):
    with scopes_disabled():
        proposal = _proposal(event, "quiet@e.com", state=ExhibitionProposalState.REJECTED)
        proposal.reopen()
        assert not ExhibitionEmailQueue.objects.filter(event=event, proposal=proposal).exists()


@pytest.mark.django_db
def test_can_be_reinstated_only_when_withdrawn(event):
    with scopes_disabled():
        assert _proposal(event, "w@e.com", state=ExhibitionProposalState.WITHDRAWN).can_be_reinstated is True
        assert _proposal(event, "s@e.com", state=ExhibitionProposalState.SUBMITTED).can_be_reinstated is False
        assert _proposal(event, "a@e.com", state=ExhibitionProposalState.ACCEPTED).can_be_reinstated is False


@pytest.mark.django_db
def test_reinstate_withdrawn_returns_to_submitted(event):
    with scopes_disabled():
        proposal = _proposal(event, "back@e.com", state=ExhibitionProposalState.WITHDRAWN)
        proposal.reopen()
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.SUBMITTED
        assert not ExhibitionEmailQueue.objects.filter(event=event, proposal=proposal).exists()
