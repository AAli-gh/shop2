import json

from django.db import transaction

from apps.orders.models import Order
from apps.payments.gateways import get_gateway
from apps.payments.models import Payment


class PaymentError(Exception):
    pass


@transaction.atomic
def start_payment(*, order: Order) -> Payment:
    """Create a gateway payment for the order and return it (redirect to intent)."""
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.PAID:
        raise PaymentError("این سفارش قبلاً پرداخت شده است")
    if order.status != Order.Status.PENDING_PAYMENT:
        raise PaymentError("این سفارش قابل پرداخت نیست")

    existing = order.payments.exclude(status=Payment.Status.FAILED).first()
    if existing and existing.status == Payment.Status.CREATED:
        payment = existing
    else:
        gateway = get_gateway()
        intent = gateway.create(order)
        payment = Payment.objects.create(
            order=order,
            provider=gateway.name,
            amount_toman=order.total,
            authority=intent.result.authority,
            status=Payment.Status.CREATED if intent.result.success else Payment.Status.FAILED,
            response=json.dumps({"create": intent.result.raw, "message": intent.result.message}, ensure_ascii=False)[:4000],
        )
        if not intent.result.success:
            raise PaymentError(intent.result.message or "خطای درگاه")
        payment._redirect_url = intent.redirect_url
    return payment


def complete_payment(*, payment: Payment, **callback_params) -> Order:
    """Verify a created payment with the gateway; settle the order once (idempotent).

    The failure is raised only after the transaction commits, so a FAILED payment
    stays recorded and the next attempt starts a fresh one.
    """
    order, error = _settle_payment(payment=payment, **callback_params)
    if error:
        raise PaymentError(error)
    return order


@transaction.atomic
def _settle_payment(*, payment: Payment, **callback_params) -> tuple[Order, str]:
    payment = Payment.objects.select_for_update().get(pk=payment.pk)
    order = Order.objects.select_for_update().get(pk=payment.order_id)
    if order.status == Order.Status.PAID:
        return order, ""  # duplicate callback — already settled
    if order.status != Order.Status.PENDING_PAYMENT:
        # e.g. expired and auto-cancelled while the customer was at the bank: never verify,
        # so the bank reverses the unverified transaction by itself.
        payment.status = Payment.Status.FAILED
        payment.response = json.dumps({"message": f"not verified: order is {order.status}"})
        payment.save(update_fields=["status", "response", "updated_at"])
        return order, "این سفارش دیگر قابل پرداخت نیست؛ اگر مبلغی از حساب شما کسر شده، طی ۷۲ ساعت توسط بانک بازگردانده می‌شود."
    if payment.status == Payment.Status.VERIFIED:
        return _mark_paid(order, payment.ref_id or payment.authority), ""

    gateway = get_gateway()
    result = gateway.verify(payment, **callback_params)
    payment.ref_id = result.ref or payment.ref_id
    payment.fee_toman = result.fee_toman if result.fee_toman is not None else payment.fee_toman
    payment.card_pan = result.card_pan or payment.card_pan
    payment.status = Payment.Status.VERIFIED if result.success else Payment.Status.FAILED
    payment.response = json.dumps({"verify": result.raw, "message": result.message}, ensure_ascii=False)[:4000]
    payment.save()

    if not result.success:
        return order, result.message or "پرداخت ناموفق بود"
    return _mark_paid(order, payment.ref_id), ""


def _mark_paid(order: Order, ref: str) -> Order:
    from apps.common import shoplog
    from apps.orders.emails import order_status_changed

    order.status = Order.Status.PAID
    order.payment_ref = ref
    order.save(update_fields=["status", "payment_ref", "updated_at"])
    shoplog.payment_verified(order, ref)
    order_status_changed(order)
    return order


# Backward-compatible name used by the simulated pay page.
@transaction.atomic
def mark_paid(*, order: Order, ref: str) -> Order:
    order = Order.objects.select_for_update().get(pk=order.pk)
    if order.status == Order.Status.PAID:
        return order
    if order.status != Order.Status.PENDING_PAYMENT:
        raise PaymentError("این سفارش قابل پرداخت نیست")
    return _mark_paid(order, ref)
