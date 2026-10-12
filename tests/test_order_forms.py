from decimal import Decimal

import pytest
from django.http import QueryDict
from django.test import Client, override_settings
from django.urls import reverse
from django.utils.timezone import now
from django_scopes import scopes_disabled
from eventyay.base.models import Event, LogEntry
from eventyay.base.models.auth import User

from exhibition.forms import ExhibitionOrderAnswersForm, ExhibitionOrderQuestionForm
from exhibition.models import (
    LOG_ORDER_FORM_ADDED,
    LOG_ORDER_QUESTION_ADDED,
    ExhibitionOrder,
    ExhibitionOrderAnswer,
    ExhibitionOrderError,
    ExhibitionOrderForm,
    ExhibitionOrderQuestion,
    ExhibitionOrderQuestionOption,
    ExhibitionProduct,
    ExhibitionProductPurpose,
    ExhibitionQuestionVariant,
    order_form_questions,
)
from exhibition.orders import place_exhibition_order


def _product(event, name, order_form=None, price="1000.00", **kwargs):
    return ExhibitionProduct.objects.create(
        event=event, name={"en": name}, price=Decimal(price), order_form=order_form, **kwargs
    )


def _question(order_form, label, variant=ExhibitionQuestionVariant.STRING, **kwargs):
    return ExhibitionOrderQuestion.objects.create(
        order_form=order_form, question={"en": label}, variant=variant, **kwargs
    )


def _choice_question(order_form, label, answers=("Yes", "No"), **kwargs):
    question = _question(order_form, label, variant=ExhibitionQuestionVariant.SELECT, **kwargs)
    options = [
        ExhibitionOrderQuestionOption.objects.create(question=question, answer={"en": answer}, position=index)
        for index, answer in enumerate(answers)
    ]
    return question, options


def _order(event, products, answers_form=None):
    return place_exhibition_order(
        event,
        products,
        name="Ada Lovelace",
        email="ada@example.com",
        payment_provider="manual",
        answers_form=answers_form,
    )


def _url(event, name, **kwargs):
    return reverse(
        f"plugins:exhibition:{name}",
        kwargs={"organizer": event.organizer.slug, "event": event.slug, **kwargs},
    )


def _organizer_client(event):
    with scopes_disabled():
        event.plugins = "exhibition"
        event.save()
        user = User.objects.create_user(
            email="organizer@example.com", password="secret", fullname="Organizer", locale="en"
        )
        team = event.organizer.teams.create(name="Organizers", all_events=True, can_change_event_settings=True)
        team.members.add(user)
    client = Client()
    client.force_login(user)
    return client


def _field_data(**overrides):
    data = QueryDict("", mutable=True)
    data.update(
        {
            "question_0": "VAT ID",
            "variant": ExhibitionQuestionVariant.STRING,
            "active": "on",
            "options-TOTAL_FORMS": "0",
            "options-INITIAL_FORMS": "0",
            "options-MIN_NUM_FORMS": "0",
            "options-MAX_NUM_FORMS": "1000",
        }
    )
    data.update(overrides)
    return data


@pytest.fixture
def forms(event):
    with scopes_disabled():
        event.settings.set("payment_manual__enabled", True)
        billing = ExhibitionOrderForm.objects.create(event=event, name="Billing")
        booth_form = ExhibitionOrderForm.objects.create(event=event, name="Booth setup")
    return {"billing": billing, "booth": booth_form}


# Which questions an order asks


@pytest.mark.django_db
def test_an_order_asks_the_questions_of_every_assigned_form_once(event, forms):
    with scopes_disabled():
        vat = _question(forms["billing"], "VAT ID")
        power = _question(forms["booth"], "Electricity")
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        silver = _product(event, "Silver Sponsor", order_form=forms["billing"])
        booth = _product(event, "Booth", order_form=forms["booth"], purpose=ExhibitionProductPurpose.EXHIBITION)

        questions = list(order_form_questions([gold, silver, booth]))

        assert questions == [vat, power]


@pytest.mark.django_db
def test_booth_questions_are_skipped_without_a_booth_product(event, forms):
    with scopes_disabled():
        logo = _question(forms["billing"], "Logo")
        furniture = _question(forms["billing"], "Furniture", booth_only=True)
        digital = _product(event, "Digital Sponsor", order_form=forms["billing"], includes_booth=False)
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])

        assert list(order_form_questions([digital])) == [logo]
        assert list(order_form_questions([gold])) == [logo, furniture]


@pytest.mark.django_db
def test_inactive_questions_and_products_without_a_form_ask_nothing(event, forms):
    with scopes_disabled():
        _question(forms["billing"], "Old question", active=False)
        plain = _product(event, "Plain Sponsor")
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])

        assert list(order_form_questions([plain])) == []
        assert list(order_form_questions([gold])) == []


# Answering at checkout


@pytest.mark.django_db
def test_answers_are_stored_with_the_order(event, forms):
    with scopes_disabled():
        vat = _question(forms["billing"], "VAT ID", required=True)
        size, (small, large) = _choice_question(forms["billing"], "Booth size", answers=("Small", "Large"))
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        answers_form = ExhibitionOrderAnswersForm(
            data={f"question_{vat.pk}": "GB123", f"question_{size.pk}": str(large.pk)},
            products=[gold],
        )

        order = _order(event, [gold], answers_form=answers_form)

        answers = {answer.question_id: answer for answer in ExhibitionOrderAnswer.objects.filter(order=order)}
        assert answers[vat.pk].answer == "GB123"
        assert list(answers[size.pk].options.all()) == [large]
        assert answers[size.pk].answer_string == "Large"


@pytest.mark.django_db
def test_a_required_question_must_be_answered(event, forms):
    with scopes_disabled():
        vat = _question(forms["billing"], "VAT ID", required=True)
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        answers_form = ExhibitionOrderAnswersForm(data={}, products=[gold])

        assert not answers_form.is_valid()
        assert f"question_{vat.pk}" in answers_form.errors
        with pytest.raises(ExhibitionOrderError):
            _order(event, [gold], answers_form=answers_form)
        assert not ExhibitionOrder.objects.exists()


@pytest.mark.django_db
def test_a_required_booth_question_does_not_block_a_digital_order(event, forms):
    with scopes_disabled():
        _question(forms["billing"], "Furniture", required=True, booth_only=True)
        digital = _product(event, "Digital Sponsor", order_form=forms["billing"], includes_booth=False)

        assert ExhibitionOrderAnswersForm(data={}, products=[digital]).is_valid()


@pytest.mark.django_db
def test_a_hidden_dependent_question_is_neither_required_nor_stored(event, forms):
    with scopes_disabled():
        needs_power, (yes, no) = _choice_question(forms["billing"], "Need electricity?")
        watts = _question(
            forms["billing"],
            "How many watts?",
            required=True,
            dependency_question=needs_power,
            dependency_values=[str(yes.pk)],
        )
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        answers_form = ExhibitionOrderAnswersForm(
            data={f"question_{needs_power.pk}": str(no.pk), f"question_{watts.pk}": "500"},
            products=[gold],
        )

        order = _order(event, [gold], answers_form=answers_form)

        assert not ExhibitionOrderAnswer.objects.filter(order=order, question=watts).exists()


@pytest.mark.django_db
def test_a_shown_dependent_question_is_required(event, forms):
    with scopes_disabled():
        needs_power, (yes, no) = _choice_question(forms["billing"], "Need electricity?")
        watts = _question(
            forms["billing"],
            "How many watts?",
            required=True,
            dependency_question=needs_power,
            dependency_values=[str(yes.pk)],
        )
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        answers_form = ExhibitionOrderAnswersForm(data={f"question_{needs_power.pk}": str(yes.pk)}, products=[gold])

        assert not answers_form.is_valid()
        assert f"question_{watts.pk}" in answers_form.errors


# Editing order form fields


@pytest.mark.django_db
def test_a_field_can_only_depend_on_fields_of_its_own_form(event, forms):
    with scopes_disabled():
        own, _ = _choice_question(forms["billing"], "Own choice")
        foreign, _ = _choice_question(forms["booth"], "Other form choice")

        form = ExhibitionOrderQuestionForm(event=event, order_form=forms["billing"])

        candidates = list(form.fields["dependency_question"].queryset)
        assert own in candidates
        assert foreign not in candidates


@pytest.mark.django_db
def test_new_fields_go_to_the_end_of_their_form(event, forms):
    with scopes_disabled():
        _question(forms["billing"], "First", position=4)
        form = ExhibitionOrderQuestionForm(data=_field_data(), event=event, order_form=forms["billing"])
        assert form.is_valid(), form.errors

        question = form.save()

        assert question.order_form == forms["billing"]
        assert question.position == 5


# Organizer pages


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_creates_an_order_form_and_adds_a_booth_field(event):
    client = _organizer_client(event)

    response = client.post(_url(event, "products.order_forms.add"), {"name": "Booth setup"})

    with scopes_disabled():
        order_form = ExhibitionOrderForm.objects.get(event=event)
        assert LogEntry.objects.filter(action_type=LOG_ORDER_FORM_ADDED, object_id=order_form.pk).exists()
    assert response.status_code == 302
    assert response.url == _url(event, "products.order_forms.fields", pk=order_form.pk)

    response = client.post(
        _url(event, "products.order_forms.fields.add", pk=order_form.pk),
        _field_data(question_0="Furniture", booth_only="on", required="on"),
    )

    assert response.status_code == 302
    with scopes_disabled():
        question = ExhibitionOrderQuestion.objects.get(order_form=order_form)
        assert question.booth_only and question.required
        assert LogEntry.objects.filter(action_type=LOG_ORDER_QUESTION_ADDED, object_id=question.pk).exists()


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_organizer_assigns_an_order_form_to_a_product(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        gold = _product(event, "Gold Sponsor")

    response = client.post(
        _url(event, "products.edit", pk=gold.pk),
        {
            "name_0": "Gold Sponsor",
            "purpose": ExhibitionProductPurpose.SPONSORSHIP,
            "includes_booth": "on",
            "price": "1000.00",
            "active": "on",
            "order_form": forms["billing"].pk,
        },
    )

    assert response.status_code == 302
    with scopes_disabled():
        assert ExhibitionProduct.objects.get(pk=gold.pk).order_form == forms["billing"]


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_order_forms_of_other_events_cannot_be_assigned_or_opened(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        other_event = Event.objects.create(
            organizer=event.organizer, name="Other Event", slug="other-event", live=True, date_from=now()
        )
        foreign = ExhibitionOrderForm.objects.create(event=other_event, name="Foreign")
        gold = _product(event, "Gold Sponsor")

    response = client.post(
        _url(event, "products.edit", pk=gold.pk),
        {
            "name_0": "Gold Sponsor",
            "purpose": ExhibitionProductPurpose.SPONSORSHIP,
            "includes_booth": "on",
            "price": "1000.00",
            "active": "on",
            "order_form": foreign.pk,
        },
    )

    assert response.status_code == 200
    assert "order_form" in response.context["form"].errors
    assert client.get(_url(event, "products.order_forms.fields", pk=foreign.pk)).status_code == 404


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_answered_forms_and_fields_cannot_be_deleted(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        vat = _question(forms["billing"], "VAT ID")
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        _order(event, [gold], ExhibitionOrderAnswersForm(data={f"question_{vat.pk}": "GB123"}, products=[gold]))

    client.post(_url(event, "products.order_forms.fields.delete", pk=forms["billing"].pk, question=vat.pk))
    client.post(_url(event, "products.order_forms.delete", pk=forms["billing"].pk))

    with scopes_disabled():
        assert ExhibitionOrderQuestion.objects.filter(pk=vat.pk).exists()
        assert ExhibitionOrderForm.objects.filter(pk=forms["billing"].pk).exists()


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_an_unanswered_form_is_deleted_and_its_products_keep_selling(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        _question(forms["billing"], "VAT ID")
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])

    response = client.post(_url(event, "products.order_forms.delete", pk=forms["billing"].pk))

    assert response.status_code == 302
    with scopes_disabled():
        assert not ExhibitionOrderForm.objects.filter(pk=forms["billing"].pk).exists()
        assert ExhibitionProduct.objects.get(pk=gold.pk).order_form is None


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_fields_can_be_reordered(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        first = _question(forms["billing"], "First", position=0)
        second = _question(forms["billing"], "Second", position=1)

    response = client.post(
        _url(event, "products.order_forms.fields.reorder", pk=forms["billing"].pk),
        {"order": f"{second.pk},{first.pk}"},
    )

    assert response.status_code == 204
    with scopes_disabled():
        assert list(forms["billing"].questions.order_by("position")) == [second, first]


@pytest.mark.django_db
@override_settings(SITE_URL="https://testserver")
def test_order_page_shows_the_answers(event, forms):
    client = _organizer_client(event)
    with scopes_disabled():
        vat = _question(forms["billing"], "VAT ID")
        gold = _product(event, "Gold Sponsor", order_form=forms["billing"])
        order = _order(
            event, [gold], ExhibitionOrderAnswersForm(data={f"question_{vat.pk}": "GB123"}, products=[gold])
        )

    content = client.get(_url(event, "orders.detail", code=order.code)).content.decode()

    assert "VAT ID" in content
    assert "GB123" in content
