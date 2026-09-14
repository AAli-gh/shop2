"""Business-event logging: one place to emit shop events to logs/shop.log."""
import logging

logger = logging.getLogger("shop")


def order_placed(order) -> None:
    logger.info(
        "ORDER_PLACED order=%s user=%s total=%s items=%s",
        order.order_number, order.user.email, order.total, order.items.count(),
    )


def order_status_changed(order, old_status: str = "") -> None:
    logger.info(
        "ORDER_STATUS order=%s user=%s %s -> %s",
        order.order_number, order.user.email, old_status, order.status,
    )


def order_cancelled(order) -> None:
    logger.info("ORDER_CANCELLED order=%s user=%s refund=%s", order.order_number, order.user.email, order.total)


def payment_verified(order, ref: str) -> None:
    logger.info("PAYMENT_OK order=%s user=%s ref=%s amount=%s", order.order_number, order.user.email, ref, order.total)


def payment_failed(order) -> None:
    logger.warning("PAYMENT_FAIL order=%s user=%s", order.order_number, order.user.email)


def user_registered(user) -> None:
    logger.info("USER_REGISTERED email=%s", user.email)


def user_verified(user) -> None:
    logger.info("USER_VERIFIED email=%s", user.email)


def product_imported(created: int, updated: int, errors: int, filename: str) -> None:
    logger.info("PRODUCT_IMPORT file=%s created=%s updated=%s errors=%s", filename, created, updated, errors)


def review_submitted(review) -> None:
    logger.info("REVIEW_SUBMITTED product=%s user=%s rating=%s", review.product_id, review.user.email, review.rating)


def newsletter_subscribed(email: str) -> None:
    logger.info("NEWSLETTER_SUBSCRIBE email=%s", email)


def order_expired(order) -> None:
    logger.info("ORDER_EXPIRED order=%s user=%s", order.order_number, order.user.email)


def refund_required(order) -> None:
    logger.warning(
        "REFUND_REQUIRED order=%s user=%s amount=%s ref=%s",
        order.order_number, order.user.email, order.total - order.wallet_used, order.payment_ref,
    )


def rate_limited(scope: str, ip: str) -> None:
    logger.warning("RATE_LIMITED scope=%s ip=%s", scope, ip)
