"""Business-event logging: one place to emit shop events to logs/shop.log."""
import logging

logger = logging.getLogger("shop")


def order_placed(order) -> None:
    logger.info(
        "ORDER_PLACED order=%s user=%s total=%s items=%s",
        order.order_number, order.user, order.total, order.items.count(),
    )


def order_status_changed(order, old_status: str = "") -> None:
    logger.info(
        "ORDER_STATUS order=%s user=%s %s -> %s",
        order.order_number, order.user, old_status, order.status,
    )


def order_cancelled(order) -> None:
    logger.info("ORDER_CANCELLED order=%s user=%s refund=%s", order.order_number, order.user, order.total)


def payment_verified(order, ref: str) -> None:
    logger.info("PAYMENT_OK order=%s user=%s ref=%s amount=%s", order.order_number, order.user, ref, order.total)


def payment_failed(order) -> None:
    logger.warning("PAYMENT_FAIL order=%s user=%s", order.order_number, order.user)


def user_registered(user) -> None:
    logger.info("USER_REGISTERED user=%s", user)


def user_verified(user) -> None:
    logger.info("USER_VERIFIED user=%s", user)


def product_imported(created: int, updated: int, errors: int, filename: str) -> None:
    logger.info("PRODUCT_IMPORT file=%s created=%s updated=%s errors=%s", filename, created, updated, errors)


def review_submitted(review) -> None:
    logger.info("REVIEW_SUBMITTED product=%s user=%s rating=%s", review.product_id, review.user, review.rating)


def newsletter_subscribed(email: str) -> None:
    logger.info("NEWSLETTER_SUBSCRIBE email=%s", email)


def order_expired(order) -> None:
    logger.info("ORDER_EXPIRED order=%s user=%s", order.order_number, order.user)


def refund_required(order) -> None:
    logger.warning(
        "REFUND_REQUIRED order=%s user=%s amount=%s ref=%s",
        order.order_number, order.user, order.total - order.wallet_used, order.payment_ref,
    )


def return_requested(return_request) -> None:
    logger.info(
        "RETURN_REQUESTED order=%s user=%s request=%s reason=%s",
        return_request.order.order_number, return_request.order.user, return_request.pk, return_request.reason,
    )


def return_status_changed(return_request, old_status: str) -> None:
    logger.info(
        "RETURN_STATUS order=%s request=%s %s -> %s",
        return_request.order.order_number, return_request.pk, old_status, return_request.status,
    )


def rate_limited(scope: str, ip: str) -> None:
    logger.warning("RATE_LIMITED scope=%s ip=%s", scope, ip)
