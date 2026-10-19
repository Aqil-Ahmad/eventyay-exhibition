import pytest
from conftest import STORED_IMAGES
from django.test import RequestFactory
from django_scopes import scopes_disabled
from eventyay.base.models.auth import User

from exhibition.filters import ExhibitorFilterForm
from exhibition.forms import ExhibitorInfoForm, ExhibitorVoucherDefaultsForm
from exhibition.models import (
    ExhibitionRequest,
    ExhibitorGroup,
    ExhibitorInfo,
    ExhibitorSettings,
    SponsorGroup,
)
from exhibition.utils import create_exhibitor_from_request, resolve_voucher_defaults
from exhibition.views import ExhibitorListView


class _User:
    is_authenticated = True

    def has_event_permission(self, organizer, event, permission, request=None):
        return True


def _organization(event, name, **kwargs):
    kwargs.setdefault("is_exhibitor", True)
    return ExhibitorInfo.objects.create(event=event, name=name, **kwargs)


def _filtered(event, **data):
    form = ExhibitorFilterForm(data=data, event=event, organization_type="exhibitor")
    assert form.is_valid(), form.errors
    queryset = ExhibitorInfo.objects.filter(event=event, is_exhibitor=True).select_related("sponsor_group")
    return [str(organization.name) for organization in form.filter_qs(queryset)]


def _download(event):
    request = RequestFactory().get("/", {"download": "yes"})
    request.event = event
    request.user = _User()
    view = ExhibitorListView(organization_type="exhibitor")
    view.request = request
    return view.get(request).content.decode("utf-8")


@pytest.mark.django_db
def test_existing_exhibitors_have_no_group_and_keep_the_event_count(event):
    with scopes_disabled():
        ExhibitorSettings.objects.create(
            event=event, voucher_default_count=3, paid_voucher_default_count=5, non_paid_voucher_default_count=2
        )
        exhibitor = _organization(event, "Acme")

        assert exhibitor.exhibitor_group == ""
        assert str(exhibitor.group_label) == "No group"
        assert resolve_voucher_defaults(exhibitor)["count"] == 3


@pytest.mark.django_db
def test_each_group_gets_its_own_voucher_count(event):
    with scopes_disabled():
        ExhibitorSettings.objects.create(event=event, paid_voucher_default_count=5, non_paid_voucher_default_count=2)
        paid = _organization(event, "Paid Co", exhibitor_group=ExhibitorGroup.PAID)
        non_paid = _organization(event, "Community Co", exhibitor_group=ExhibitorGroup.NON_PAID)

        assert resolve_voucher_defaults(paid)["count"] == 5
        assert resolve_voucher_defaults(non_paid)["count"] == 2


@pytest.mark.django_db
def test_a_sponsor_with_a_booth_shows_and_uses_its_sponsor_group(event):
    with scopes_disabled():
        ExhibitorSettings.objects.create(event=event, paid_voucher_default_count=5)
        gold = SponsorGroup.objects.create(event=event, name="Gold", voucher_default_count=9)
        organization = _organization(
            event, "Acme", is_sponsor=True, sponsor_group=gold, exhibitor_group=ExhibitorGroup.PAID
        )

        assert str(organization.group_label) == "Sponsor · Gold"
        assert resolve_voucher_defaults(organization)["count"] == 9

        organization.is_sponsor = False
        organization.sponsor_group = None
        organization.save()

        assert str(organization.group_label) == "Paid exhibitor"
        assert resolve_voucher_defaults(organization)["count"] == 5


@pytest.mark.django_db
def test_voucher_settings_offer_one_count_per_group(event):
    with scopes_disabled():
        form = ExhibitorVoucherDefaultsForm(event=event)

    assert "paid_voucher_default_count" in form.fields
    assert "non_paid_voucher_default_count" in form.fields
    assert "voucher_default_count" not in form.fields


@pytest.mark.django_db
def test_an_accepted_request_becomes_a_non_paid_exhibitor(event):
    with scopes_disabled():
        user = User.objects.create_user(email="applicant@example.com", password="secret")
        exhibition_request = ExhibitionRequest.objects.create(event=event, user=user, name="Acme", is_exhibitor=True)

        exhibitor = create_exhibitor_from_request(exhibition_request)

        assert exhibitor.exhibitor_group == ExhibitorGroup.NON_PAID


@pytest.mark.django_db
def test_reapproving_keeps_the_group_the_organiser_chose(event):
    with scopes_disabled():
        user = User.objects.create_user(email="applicant@example.com", password="secret")
        exhibitor = _organization(event, "Acme", exhibitor_group=ExhibitorGroup.PAID)
        exhibition_request = ExhibitionRequest.objects.create(
            event=event, user=user, name="Acme", is_exhibitor=True, approved_exhibitor=exhibitor
        )

        create_exhibitor_from_request(exhibition_request)

        exhibitor.refresh_from_db()
        assert exhibitor.exhibitor_group == ExhibitorGroup.PAID


@pytest.mark.django_db
def test_adding_an_exhibitor_needs_a_group(event, image_uploads):
    with scopes_disabled():
        form = ExhibitorInfoForm(
            data={"name_0": "Acme"}, files=image_uploads(), event=event, organization_type="exhibitor"
        )
        assert "exhibitor_group" in form.fields
        assert not form.fields["exhibitor_group"].initial
        assert [value for value, label in form.fields["exhibitor_group"].choices] == ["paid", "non_paid"]
        assert not form.is_valid()
        assert "exhibitor_group" in form.errors

        form = ExhibitorInfoForm(
            data={"name_0": "Acme", "exhibitor_group": "paid"},
            files=image_uploads(),
            event=event,
            organization_type="exhibitor",
        )
        assert form.is_valid(), form.errors
        exhibitor = form.save(commit=False)

    assert exhibitor.exhibitor_group == ExhibitorGroup.PAID


@pytest.mark.django_db
def test_adding_a_sponsor_needs_no_group(event, image_uploads):
    with scopes_disabled():
        form = ExhibitorInfoForm(
            data={"name_0": "Acme"}, files=image_uploads(), event=event, organization_type="sponsor"
        )

        assert "exhibitor_group" not in form.fields
        assert form.is_valid(), form.errors


@pytest.mark.django_db
def test_an_exhibitor_without_a_group_can_be_edited_and_given_one(event):
    with scopes_disabled():
        ExhibitorSettings.objects.create(event=event)
        exhibitor = _organization(event, "Acme", **STORED_IMAGES)

        form = ExhibitorInfoForm(
            data={"name_0": "Acme"}, instance=exhibitor, event=event, organization_type="exhibitor"
        )
        assert "" in [value for value, label in form.fields["exhibitor_group"].choices]
        assert form.is_valid(), form.errors
        form.save()
        exhibitor.refresh_from_db()
        assert exhibitor.exhibitor_group == ""

        form = ExhibitorInfoForm(
            data={"name_0": "Acme", "exhibitor_group": "non_paid"},
            instance=exhibitor,
            event=event,
            organization_type="exhibitor",
        )
        assert form.is_valid(), form.errors
        form.save()
        exhibitor.refresh_from_db()
        assert exhibitor.exhibitor_group == ExhibitorGroup.NON_PAID

        form = ExhibitorInfoForm(
            data={"name_0": "Acme Renamed", "exhibitor_group": "non_paid"},
            instance=exhibitor,
            event=event,
            organization_type="exhibitor",
        )
        assert "" not in [value for value, label in form.fields["exhibitor_group"].choices]
        assert form.is_valid(), form.errors
        form.save()
        exhibitor.refresh_from_db()
        assert exhibitor.exhibitor_group == ExhibitorGroup.NON_PAID


@pytest.mark.django_db
def test_the_group_filter_separates_sponsors_and_exhibitor_groups(event):
    with scopes_disabled():
        gold = SponsorGroup.objects.create(event=event, name="Gold", level=1)
        _organization(event, "Gold Co", is_sponsor=True, sponsor_group=gold, exhibitor_group=ExhibitorGroup.PAID)
        _organization(event, "Paid Co", exhibitor_group=ExhibitorGroup.PAID)
        _organization(event, "Community Co", exhibitor_group=ExhibitorGroup.NON_PAID)
        _organization(event, "Old Co")

        assert _filtered(event, group="paid") == ["Paid Co"]
        assert _filtered(event, group="non_paid") == ["Community Co"]
        assert _filtered(event, group="none") == ["Old Co"]
        assert _filtered(event, group="sponsors") == ["Gold Co"]
        assert _filtered(event, group=f"sponsor-{gold.pk}") == ["Gold Co"]


@pytest.mark.django_db
def test_sorting_by_group_lists_sponsors_by_level_then_paid_non_paid_and_ungrouped(event):
    with scopes_disabled():
        gold = SponsorGroup.objects.create(event=event, name="Gold", level=1)
        silver = SponsorGroup.objects.create(event=event, name="Silver", level=2)
        _organization(event, "Old Co")
        _organization(event, "Community Co", exhibitor_group=ExhibitorGroup.NON_PAID)
        _organization(event, "Silver Co", is_sponsor=True, sponsor_group=silver)
        _organization(event, "Paid Co", exhibitor_group=ExhibitorGroup.PAID)
        _organization(event, "Gold Co", is_sponsor=True, sponsor_group=gold)

        assert _filtered(event, ordering="group") == ["Gold Co", "Silver Co", "Paid Co", "Community Co", "Old Co"]


@pytest.mark.django_db
def test_the_export_lists_each_organizations_group(event):
    with scopes_disabled():
        gold = SponsorGroup.objects.create(event=event, name="Gold")
        _organization(event, "Gold Co", is_sponsor=True, sponsor_group=gold)
        _organization(event, "Paid Co", exhibitor_group=ExhibitorGroup.PAID)
        _organization(event, "Old Co")

        body = _download(event)

    assert "Group" in body.splitlines()[0]
    assert "Sponsor · Gold" in body
    assert "Paid exhibitor" in body
    assert "No group" in body
