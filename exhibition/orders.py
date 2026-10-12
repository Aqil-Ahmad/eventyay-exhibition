from datetime import timedelta
from decimal import Decimal

from django.db import transaction
from django.utils import timezone
from django.utils.translation import gettext as _

from .models import (
    LOG_ORDER_PLACED,
    ExhibitionOrder,
    ExhibitionOrderError,
    ExhibitionOrderPosition,
    ExhibitionOrderStateError,
    ExhibitionOrderStatus,
    ExhibitionProduct,
    reserve_quota_capacity,
)

SUPPORTED_PAYMENT_PROVIDERS = ("manual", "banktransfer")
FREE_PAYMENT_PROVIDER = "free"


def usable_payment_providers(event):
    """The event's enabled payment methods that exhibition orders can be paid with."""
    return {
        identifier: provider
        for identifier, provider in event.get_payment_providers().items()
        if identifier in SUPPORTED_PAYMENT_PROVIDERS and provider.is_enabled
    }


def payment_method_names(event):
    """The display name of every payment method an exhibition order can carry, keyed by identifier."""
    names = {identifier: str(provider.verbose_name) for identifier, provider in event.get_payment_providers().items()}
    names[FREE_PAYMENT_PROVIDER] = _("Free")
    return names


def paid_products_lack_payment_method(event):
    """Whether active products with a price are on offer while no usable payment method is enabled."""
    return (
        ExhibitionProduct.objects.filter(event=event, active=True, price__gt=0).exists()
        and not usable_payment_providers(event)
    )


def place_exhibition_order(
    event,
    products,
    *,
    name,
    email,
    organization_name="",
    phone="",
    answers_form=None,
    payment_provider="",
    user=None,
):
    """Place an order at current prices with the answers of ``answers_form``; a free order is paid at once."""
    products = list(products)
    if not products:
        raise ExhibitionOrderError("An order needs at least one product.")
    if answers_form is not None and not answers_form.is_valid():
        raise ExhibitionOrderError("The order form has errors.")

    now = timezone.now()
    for product in products:
        if product.event_id != event.pk or not product.is_available(now):
            raise ExhibitionOrderError(f"{product} is not on sale.")

    total = sum((product.price for product in products), Decimal("0.00"))
    if total and payment_provider not in usable_payment_providers(event):
        raise ExhibitionOrderError("The payment method is not available for this event.")

    with transaction.atomic():
        reserve_quota_capacity(products)
        order = ExhibitionOrder.objects.create(
            event=event,
            organization_name=organization_name,
            name=name,
            email=email,
            phone=phone,
            total=total,
            payment_provider=payment_provider if total else "",
            expires=now + timedelta(days=event.settings.get("payment_term_days", as_type=int)) if total else None,
        )
        ExhibitionOrderPosition.objects.bulk_create(
            ExhibitionOrderPosition(order=order, product=product, price=product.price) for product in products
        )
        if answers_form is not None:
            answers_form.save_exhibition_questions(order)
        order.log_action(
            LOG_ORDER_PLACED,
            data={"total": str(total), "products": [product.pk for product in products]},
            user=user,
        )
        if not total:
            order.mark_paid(provider=FREE_PAYMENT_PROVIDER, user=user)
    return order


def expire_overdue_orders(now=None):
    """Expire pending orders whose payment term has passed and return how many were expired."""
    overdue = ExhibitionOrder.objects.filter(
        status=ExhibitionOrderStatus.PENDING,
        expires__lt=now or timezone.now(),
    ).select_related("event")
    expired = 0
    for order in overdue:
        try:
            order.expire()
        except ExhibitionOrderStateError:
            continue
        expired += 1
    return expired
