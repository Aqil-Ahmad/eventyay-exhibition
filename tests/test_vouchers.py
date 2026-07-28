from types import SimpleNamespace

import pytest
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models import PriceModeChoices, Product, Voucher

from exhibition.api import VoucherRedemptionRetrieveView, get_allowed_attendee_data
from exhibition.forms import ExhibitorVoucherBatchForm
from exhibition.models import ExhibitorInfo, ExhibitorVoucher
from exhibition.utils import generate_exhibitor_vouchers


def _exhibitor(event, **kwargs):
    return ExhibitorInfo.objects.create(event=event, name=kwargs.pop("name", "Acme"), **kwargs)


def _product(event):
    return Product.objects.create(event=event, name="Ticket", default_price=10, active=True)


def _retrieve(event, key):
    request = RequestFactory().get("/", HTTP_EXHIBITOR=key or "")
    request.event = event
    view = VoucherRedemptionRetrieveView()
    view.request = request
    return view.get(request, organizer=event.organizer.slug, event=event.slug)


@pytest.mark.django_db
def test_generate_exhibitor_vouchers_creates_links_and_vouchers(event):
    with scopes_disabled():
        exhibitor = _exhibitor(event)
        product = _product(event)
        generate_exhibitor_vouchers(
            exhibitor,
            product=product,
            count=3,
            max_usages=2,
            price_mode=PriceModeChoices.PERCENT,
            value=100,
            valid_until=None,
        )
        links = ExhibitorVoucher.objects.filter(exhibitor=exhibitor)
        assert links.count() == 3
        voucher = links.first().voucher
        assert voucher.max_usages == 2
        assert voucher.price_mode == PriceModeChoices.PERCENT
        assert voucher.tag == f"exhibitor-{exhibitor.key}"
        assert Voucher.objects.filter(event=event).count() == 3


@pytest.mark.django_db
def test_batch_form_requires_value_for_non_none_price_mode(event):
    with scopes_disabled():
        product = _product(event)
        form = ExhibitorVoucherBatchForm(
            data={"product": product.pk, "count": 1, "max_usages": 1, "price_mode": PriceModeChoices.PERCENT},
            event=event,
        )
        assert not form.is_valid()
        assert "value" in form.errors


@pytest.mark.django_db
def test_batch_form_limits_products_to_event(event):
    with scopes_disabled():
        product = _product(event)
        form = ExhibitorVoucherBatchForm(event=event)
        assert list(form.fields["product"].queryset) == [product]


def _settings(*allowed):
    allowed = set(allowed)
    return SimpleNamespace(is_field_allowed=lambda key: key in allowed)


def _position():
    no_questions = SimpleNamespace(filter=lambda **kwargs: SimpleNamespace(order_by=lambda *args: []))
    return SimpleNamespace(
        attendee_name="N",
        attendee_email="e@x.com",
        company="Acme",
        job_title="",
        street="",
        zipcode="",
        city="",
        country="",
        answers=SimpleNamespace(all=lambda: []),
        order=SimpleNamespace(event=SimpleNamespace(questions=no_questions)),
    )


def test_attendee_data_gates_company_when_not_allowed():
    data = get_allowed_attendee_data(_position(), _settings("attendee_name", "attendee_email"))
    assert data == {"name": "N", "email": "e@x.com"}


def test_attendee_data_includes_company_when_allowed():
    data = get_allowed_attendee_data(
        _position(), _settings("attendee_name", "attendee_email", "system_company")
    )
    assert data["company"] == "Acme"


@pytest.mark.django_db
def test_retrieve_rejects_invalid_key(event):
    with scopes_disabled():
        response = _retrieve(event, "nope")
        assert response.status_code == 401


@pytest.mark.django_db
def test_retrieve_forbidden_when_access_disabled(event):
    with scopes_disabled():
        exhibitor = _exhibitor(event, allow_voucher_access=False)
        response = _retrieve(event, exhibitor.key)
        assert response.status_code == 403


@pytest.mark.django_db
def test_retrieve_allows_when_access_enabled(event):
    with scopes_disabled():
        exhibitor = _exhibitor(event, allow_voucher_access=True)
        response = _retrieve(event, exhibitor.key)
        assert response.status_code == 200
        assert response.data["success"] is True
        assert response.data["redemptions"] == []
