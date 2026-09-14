"""Payment gateway contract.

To plug in a real gateway later, set in .env:
    PAYMENT_GATEWAY=apps.payments.gateways.ZarinPalGateway
    ZARINPAL_MERCHANT_ID=xxxxxxxx-xxxx-xxxx-xxxx-xxxxxxxxxxxx
    ZARINPAL_SANDBOX=False   # در پروداکشن

`Payment` rows record every attempt (create/verify/fail), so callbacks stay
idempotent and support can inspect the raw provider response.
"""
import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field

from django.conf import settings
from django.urls import reverse


@dataclass
class PaymentResult:
    success: bool
    authority: str = ""
    ref: str = ""
    fee_toman: int | None = None
    card_pan: str = ""
    message: str = ""
    raw: str = ""


@dataclass
class PaymentIntent:
    redirect_url: str
    result: PaymentResult = field(default=None)


class PaymentGateway(ABC):
    name = "base"

    @abstractmethod
    def create(self, order) -> PaymentIntent:
        """Reserve a payment with the provider and return where to send the browser."""

    @abstractmethod
    def verify(self, payment, **callback_params) -> PaymentResult:
        """Server-side verification after the user returns from the bank."""

    @abstractmethod
    def redirect_for_payment(self, payment) -> str:
        """URL for an already-created payment (e.g. user returns to the pay page later)."""

    def callback_url(self, order) -> str:
        return settings.SITE_URL.rstrip("/") + reverse(
            "payments:callback", kwargs={"order_number": order.order_number}
        )

    def pay_page_url(self, order) -> str:
        return reverse("orders:pay", kwargs={"order_number": order.order_number})


class MockGateway(PaymentGateway):
    """Simulated gateway that keeps the existing checkout flow intact.

    create() points at the internal pay page; verify() succeeds unless the
    page was submitted with outcome=fail (the simulated failure button).
    """

    name = "mock"

    def create(self, order) -> PaymentIntent:
        return PaymentIntent(
            redirect_url=self.pay_page_url(order),
            result=PaymentResult(success=True, authority=f"MOCK-{uuid.uuid4().hex[:10]}"),
        )

    def redirect_for_payment(self, payment) -> str:
        return self.pay_page_url(payment.order)

    def verify(self, payment, **callback_params) -> PaymentResult:
        outcome = (callback_params.get("outcome") or "success").lower()
        if outcome != "success":
            return PaymentResult(success=False, message="پرداخت ناموفق (شبیه‌سازی)")
        return PaymentResult(success=True, ref=f"MOCK-{uuid.uuid4().hex[:10].upper()}", message="پرداخت شبیه‌سازی‌شده موفق بود")


class ZarinPalGateway(PaymentGateway):
    """ZarinPal v4 (REST). Amounts are Toman in our DB, Rial at the gateway."""

    name = "zarinpal"

    def __init__(self):
        cfg = getattr(settings, "ZARINPAL", {})
        self.merchant_id = cfg.get("MERCHANT_ID", "")
        self.sandbox = cfg.get("SANDBOX", True)
        host = "sandbox.zarinpal.com" if self.sandbox else "api.zarinpal.com"
        pay_host = "sandbox.zarinpal.com" if self.sandbox else "www.zarinpal.com"
        self.base = f"https://{host}/pg/v4/payment"
        self.start_pay = f"https://{pay_host}/pg/StartPay"

    def _client(self):
        import requests

        return requests

    def create(self, order) -> PaymentIntent:
        if not self.merchant_id:
            raise RuntimeError("ZARINPAL_MERCHANT_ID تنظیم نشده است")
        payload = {
            "merchant_id": self.merchant_id,
            "amount": order.total * 10,  # Rial
            "description": f"سفارش {order.order_number}"[:100],
            "callback_url": self.callback_url(order),
        }
        resp = self._client().post(f"{self.base}/request.json", json=payload, timeout=15)
        data = resp.json()
        authority = (data.get("data") or {}).get("authority", "")
        ok = resp.status_code == 200 and authority
        result = PaymentResult(
            success=bool(ok), authority=authority, raw=resp.text[:4000],
            message="" if ok else (data.get("errors") or {}).get("error_message") or "خطا در ایجاد پرداخت",
        )
        url = f"{self.start_pay}/{authority}" if ok else self.callback_url(order)
        return PaymentIntent(redirect_url=url, result=result)

    def redirect_for_payment(self, payment) -> str:
        return f"{self.start_pay}/{payment.authority}"

    def verify(self, payment, **callback_params) -> PaymentResult:
        status = (callback_params.get("Status") or callback_params.get("status") or "").upper()
        if status and status not in ("OK", "100"):
            return PaymentResult(success=False, message="کاربر پرداخت را در بانک تکمیل نکرد", raw=status)
        payload = {
            "merchant_id": self.merchant_id,
            "authority": payment.authority,
            "amount": payment.amount_toman * 10,
        }
        resp = self._client().post(f"{self.base}/verify.json", json=payload, timeout=15)
        data = resp.json()
        inner = data.get("data") or {}
        code = inner.get("code")
        ok = code in (100, 101)  # 101 = قبلاً تأیید شده — idempotent
        result = PaymentResult(
            success=bool(ok),
            ref=str(inner.get("ref_id", "")),
            fee_toman=int(round((inner.get("fee") or 0) / 10)) or None,  # Rial -> Toman
            card_pan=str(inner.get("card_pan", "")),
            message="" if ok else (data.get("errors") or {}).get("error_message") or "تأیید ناموفق",
            raw=resp.text[:4000],
        )
        return result


def get_gateway() -> PaymentGateway:
    dotted_path = settings.PAYMENT_GATEWAY
    module_path, _, class_name = dotted_path.rpartition(".")
    import importlib

    module = importlib.import_module(module_path)
    return getattr(module, class_name)()
