import pytest
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.models import ExhibitionProposal, ExhibitionProposalState
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
def test_can_be_withdrawn_only_for_submitted_and_accepted(event):
    with scopes_disabled():
        assert _proposal(event, "s@e.com", state=ExhibitionProposalState.SUBMITTED).can_be_withdrawn is True
        assert _proposal(event, "a@e.com", state=ExhibitionProposalState.ACCEPTED).can_be_withdrawn is True
        assert _proposal(event, "d@e.com", state=ExhibitionProposalState.DRAFT).can_be_withdrawn is False
        assert _proposal(event, "r@e.com", state=ExhibitionProposalState.REJECTED).can_be_withdrawn is False
        assert _proposal(event, "w@e.com", state=ExhibitionProposalState.WITHDRAWN).can_be_withdrawn is False


@pytest.mark.django_db
def test_withdraw_submitted_sets_state(event):
    with scopes_disabled():
        proposal = _proposal(event, "sub@e.com")
        proposal.withdraw()
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.WITHDRAWN
        assert proposal.approved_exhibitor_id is None


@pytest.mark.django_db
def test_withdraw_accepted_deactivates_partner_without_deleting(event):
    with scopes_disabled():
        proposal = _proposal(event, "acc@e.com")
        exhibitor = create_exhibitor_from_proposal(proposal)
        proposal.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.ACCEPTED
        assert proposal.approved_exhibitor_id == exhibitor.pk
        assert exhibitor.active is True

        proposal.withdraw()
        proposal.refresh_from_db()
        exhibitor.refresh_from_db()
        assert proposal.state == ExhibitionProposalState.WITHDRAWN
        assert proposal.approved_exhibitor_id == exhibitor.pk
        assert exhibitor.active is False


@pytest.mark.django_db
def test_withdrawn_partner_hidden_from_public_queryset(event):
    from exhibition.utils import public_exhibitors_queryset

    with scopes_disabled():
        proposal = _proposal(event, "pub@e.com")
        proposal.logo_url = "https://example.com/logo.png"
        proposal.header_image_url = "https://example.com/header.png"
        proposal.save(update_fields=["logo_url", "header_image_url"])
        exhibitor = create_exhibitor_from_proposal(proposal)
        assert exhibitor in public_exhibitors_queryset(event)

        proposal.refresh_from_db()
        proposal.withdraw()
        assert exhibitor not in public_exhibitors_queryset(event)
