import logging

from django.contrib import messages
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render

from apps.orders.models import Order
from apps.payments import services
from apps.payments.gateways import get_gateway
from apps.payments.models import Payment
from apps.payments.services import PaymentError

logger = logging.getLogger("shop")


def callback(request, order_number):
    """Gateway redirect target (works for real gateways and the mock).

    The payment is looked up by the authority/RefID the bank sends back, so a
    user refreshing or replaying this URL can never double-settle an order —
    complete_payment() is idempotent.
    """
    if get_gateway().name == "mock":
        # the simulated bank settles on its own pay page, for the signed-in owner only;
        # here anyone holding an order number could mark it paid
        raise Http404("درگاه شبیه‌ساز از این مسیر پشتیبانی نمی‌کند")
    authority = request.GET.get("Authority") or request.GET.get("authority") or ""
    order = get_object_or_404(Order, order_number=order_number)
    payment = None
    if authority:
        payment = Payment.objects.filter(authority=authority, order=order).first()
    if payment is None:
        payment = order.payments.filter(status=Payment.Status.CREATED).order_by("-created_at").first()
    if payment is None:
        # no pending payment: maybe already paid — send to the right place
        if order.status == Order.Status.PAID:
            return redirect("orders:success", order_number=order.order_number)
        raise Http404("پرداختی برای این سفارش پیدا نشد")

    try:
        services.complete_payment(payment=payment, **request.GET.dict())
    except PaymentError as exc:
        logger.warning("PAYMENT_FAIL order=%s reason=%s", order.order_number, exc)
        messages.error(request, f"پرداخت انجام نشد: {exc}")
        return redirect("orders:detail", order_number=order.order_number)

    return redirect("orders:success", order_number=order.order_number)
