"""Return (مرجوعی) requests for delivered orders."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Sum
from django.utils import timezone

from apps.orders.models import Order, ReturnRequest, ReturnRequestItem


class ReturnError(Exception):
    pass


ALLOWED_TRANSITIONS = {
    ReturnRequest.Status.PENDING: {ReturnRequest.Status.APPROVED, ReturnRequest.Status.REJECTED},
    ReturnRequest.Status.APPROVED: {ReturnRequest.Status.RECEIVED, ReturnRequest.Status.REJECTED},
    ReturnRequest.Status.RECEIVED: {ReturnRequest.Status.COMPLETED},
    ReturnRequest.Status.COMPLETED: set(),
    ReturnRequest.Status.REJECTED: set(),
}


def return_deadline(order: Order):
    if order.delivered_at is None:
        return None
    return order.delivered_at + timedelta(days=settings.RETURN_WINDOW_DAYS)


def return_block_reason(order: Order) -> str:
    """Why the customer can't open a return right now, or "" if they can."""
    if order.status != Order.Status.DELIVERED:
        return "درخواست مرجوعی پس از تحویل سفارش امکان‌پذیر است."
    deadline = return_deadline(order)
    if deadline is None or timezone.now() > deadline:
        return f"مهلت {settings.RETURN_WINDOW_DAYS} روزه ثبت درخواست مرجوعی برای این سفارش تمام شده است."
    if order.return_requests.filter(status__in=ReturnRequest.OPEN_STATUSES).exists():
        return "برای این سفارش یک درخواست مرجوعی در حال بررسی دارید."
    return ""


def returnable_quantities(order: Order) -> dict[int, int]:
    """Order item id -> units still returnable (ordered minus units in requests that weren't rejected)."""
    claimed = (
        ReturnRequestItem.objects.filter(order_item__order=order)
        .exclude(return_request__status=ReturnRequest.Status.REJECTED)
        .values("order_item")
        .annotate(units=Sum("quantity"))
    )
    used = {row["order_item"]: row["units"] for row in claimed}
    return {item.pk: item.quantity - used.get(item.pk, 0) for item in order.items.all()}


def create_return_request(*, order: Order, quantities: dict[int, int], reason: str, resolution: str,
                          description: str, image=None) -> ReturnRequest:
    return_request = _create(
        order=order, quantities=quantities, reason=reason, resolution=resolution,
        description=description, image=image,
    )
    from apps.common import shoplog
    from apps.orders.emails import return_requested

    shoplog.return_requested(return_request)
    return_requested(return_request)
    return return_request


@transaction.atomic
def _create(*, order, quantities, reason, resolution, description, image):
    order = Order.objects.select_for_update().get(pk=order.pk)
    blocked = return_block_reason(order)
    if blocked:
        raise ReturnError(blocked)

    chosen = {item_id: qty for item_id, qty in quantities.items() if qty > 0}
    if not chosen:
        raise ReturnError("حداقل یک کالا و تعداد آن را برای مرجوعی انتخاب کنید.")
    available = returnable_quantities(order)
    for item_id, qty in chosen.items():
        if item_id not in available:
            raise ReturnError("کالای انتخاب‌شده در این سفارش نیست.")
        if qty > available[item_id]:
            raise ReturnError("تعداد انتخاب‌شده بیشتر از تعداد قابل مرجوع است.")

    return_request = ReturnRequest.objects.create(
        order=order, reason=reason, resolution=resolution, description=description, image=image or "",
    )
    ReturnRequestItem.objects.bulk_create([
        ReturnRequestItem(return_request=return_request, order_item_id=item_id, quantity=qty)
        for item_id, qty in chosen.items()
    ])
    return return_request


def set_return_status(*, return_request: ReturnRequest, status: str, staff_note: str | None = None) -> ReturnRequest:
    """Move a request along its workflow and tell the customer."""
    with transaction.atomic():
        current = ReturnRequest.objects.select_for_update().select_related("order__user").get(pk=return_request.pk)
        if status not in ALLOWED_TRANSITIONS.get(current.status, set()):
            raise ReturnError(
                f"تغییر وضعیت از «{current.get_status_display()}» به «{ReturnRequest.Status(status).label}» مجاز نیست."
            )
        old_status = current.status
        current.status = status
        if staff_note is not None:
            current.staff_note = staff_note
        current.save(update_fields=["status", "staff_note", "updated_at"])

    from apps.common import shoplog
    from apps.orders.emails import return_status_changed

    shoplog.return_status_changed(current, old_status)
    return_status_changed(current)
    return current
