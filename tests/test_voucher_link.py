from datetime import timedelta

import pytest
from django.contrib.messages.storage.fallback import FallbackStorage
from django.contrib.sessions.backends.db import SessionStore
from django.http import Http404
from django.test import RequestFactory
from django.utils.timezone import now
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.models import ExhibitionRequest, ExhibitionRequestState, ExhibitorInfo
from exhibition.utils import exhibitor_for_voucher_link, exhibitor_voucher_link
from exhibition.views import ExhibitorVoucherLinkRegenerateView, ExhibitorVoucherLinkView


def _organizer_created(event, **kwargs):
    kwargs.setdefault("allow_voucher_access", True)
    return ExhibitorInfo.objects.create(event=event, name="Acme", **kwargs)


def _request_based(event):
    exhibitor = _organizer_created(event)
    user = User.objects.create_user(email="applicant@example.com", password="pw")
    ExhibitionRequest.objects.create(
        event=event,
        user=user,
        name="Acme",
        state=ExhibitionRequestState.ACCEPTED,
        approved_exhibitor=exhibitor,
    )
    return exhibitor


def _link_view(event, token):
    request = RequestFactory().get("/")
    request.event = event
    request.user = None
    view = ExhibitorVoucherLinkView()
    view.request = request
    view.kwargs = {"token": token}
    view.args = ()
    return view, request


@pytest.mark.django_db
def test_link_opens_an_organizer_created_exhibitor(event):
    with scopes_disabled():
        exhibitor = _organizer_created(event)

        assert exhibitor_for_voucher_link(event, exhibitor.voucher_link_token) == exhibitor


@pytest.mark.django_db
def test_link_does_not_open_a_request_based_exhibitor(event):
    with scopes_disabled():
        exhibitor = _request_based(event)

        assert exhibitor_for_voucher_link(event, exhibitor.voucher_link_token) is None


@pytest.mark.django_db
@pytest.mark.parametrize("change", [{"allow_voucher_access": False}, {"active": False}])
def test_link_stops_working_when_access_is_withdrawn(event, change):
    with scopes_disabled():
        exhibitor = _organizer_created(event, **change)

        assert exhibitor_for_voucher_link(event, exhibitor.voucher_link_token) is None


@pytest.mark.django_db
def test_link_expires_a_while_after_the_event(event):
    with scopes_disabled():
        exhibitor = _organizer_created(event)
        event.date_from = now() - timedelta(days=60)
        event.date_to = now() - timedelta(days=31)
        event.save(update_fields=["date_from", "date_to"])

        assert exhibitor_for_voucher_link(event, exhibitor.voucher_link_token) is None


@pytest.mark.django_db
def test_unknown_token_returns_404(event):
    with scopes_disabled():
        _organizer_created(event)
        view, request = _link_view(event, "not-a-real-token")

        with pytest.raises(Http404):
            view.dispatch(request)


@pytest.mark.django_db
def test_link_page_keeps_the_token_out_of_referers_and_caches(event):
    with scopes_disabled():
        exhibitor = _organizer_created(event)
        view, request = _link_view(event, exhibitor.voucher_link_token)

        response = view.dispatch(request)

        assert response["Referrer-Policy"] == "no-referrer"
        assert response["Cache-Control"] == "no-store"
        assert "noindex" in response["X-Robots-Tag"]


@pytest.mark.django_db
def test_email_link_points_each_exhibitor_to_its_own_page(event):
    with scopes_disabled():
        organizer_created = _organizer_created(event)
        request_based = _request_based(event)

        assert f"/exhibition/vouchers/{organizer_created.voucher_link_token}/" in exhibitor_voucher_link(
            organizer_created
        )
        request_link = exhibitor_voucher_link(request_based)
        assert "/exhibition/call/requests/" in request_link
        assert request_based.voucher_link_token not in request_link


@pytest.mark.django_db
def test_regenerating_invalidates_the_previous_link(event):
    with scopes_disabled():
        exhibitor = _organizer_created(event)
        old_token = exhibitor.voucher_link_token

        request = RequestFactory().post("/")
        request.event = event
        request.user = User.objects.create_user(email="organizer@example.com", password="pw")
        request.session = SessionStore()
        request._messages = FallbackStorage(request)
        view = ExhibitorVoucherLinkRegenerateView()
        view.request = request
        view.post(request, pk=exhibitor.pk)

        exhibitor.refresh_from_db()
        assert exhibitor.voucher_link_token != old_token
        assert exhibitor_for_voucher_link(event, old_token) is None
        assert exhibitor_for_voucher_link(event, exhibitor.voucher_link_token) == exhibitor
