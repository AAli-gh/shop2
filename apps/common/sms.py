"""SMS delivery behind a swappable backend (same idea as the payment gateway).

Development writes messages to sent_sms/; production uses SMS.ir:
    SMS_BACKEND=apps.common.sms.SmsIrBackend
    SMSIR_API_KEY=...            SMSIR_OTP_TEMPLATE_ID=...   (approved Verify template)
    SMSIR_LINE_NUMBER=...        (plain texts, for notifications without a template)
    SMSIR_TEMPLATE_<EVENT>=...   (optional Verify template per notification, see EVENT_PARAMETERS)

Texts from a line don't reach numbers on the operators' blacklist (people who blocked
advertising SMS); Verify templates do, which is why every notification can use one.
"""
import importlib
import logging
from abc import ABC, abstractmethod
from datetime import datetime
from pathlib import Path

from django.conf import settings

logger = logging.getLogger("shop")

# Each notification event and the parameters its SMS.ir template receives (#ORDER#, #AMOUNT#, ...).
EVENT_PARAMETERS = {
    "order_placed": ("ORDER", "AMOUNT"),
    "order_status": ("ORDER", "STATUS"),
    "return_status": ("ORDER", "STATUS"),
    "order_paid_staff": ("ORDER", "AMOUNT"),
    "low_stock": ("PRODUCT", "COUNT"),
    "cart_reminder": ("COUNT",),
    "price_drop": ("PRODUCT", "PRICE"),
    "question_answered": ("PRODUCT",),
    "review_request": ("PRODUCT",),
    "winback": ("CODE", "PERCENT", "DAYS"),
}
# template parameter values are kept short (long product names are cut)
PARAM_MAX_LENGTH = 25


class SmsError(Exception):
    pass


class SmsBackend(ABC):
    @abstractmethod
    def send_otp(self, phone: str, code: str) -> None:
        """Deliver a login code; raise SmsError on failure."""

    @abstractmethod
    def send_text(self, phone: str, text: str) -> None:
        """Deliver a plain notification; raise SmsError on failure."""

    def send_event(self, phone: str, event: str, params: dict, text: str) -> None:
        """Deliver a notification through its template when there is one, else as the plain text."""
        self.send_text(phone, text)


class FileSmsBackend(SmsBackend):
    """Development backend: appends each message to sent_sms/<date>.log instead of sending it."""

    def _write(self, phone: str, text: str) -> None:
        folder = Path(settings.SMS_FILE_PATH)
        folder.mkdir(parents=True, exist_ok=True)
        now = datetime.now()
        with open(folder / f"{now:%Y%m%d}.log", "a", encoding="utf-8") as fh:
            fh.write(f"[{now:%H:%M:%S}] to={phone}\n{text}\n\n")

    def send_otp(self, phone, code):
        self._write(phone, f"کد ورود شما: {code}")

    def send_text(self, phone, text):
        self._write(phone, text)

    def send_event(self, phone, event, params, text):
        self._write(phone, f"{text}\n[{event}: {params}]")


class LocmemSmsBackend(SmsBackend):
    """Test backend: messages are kept in LocmemSmsBackend.outbox."""

    outbox: list[dict] = []

    def send_otp(self, phone, code):
        self.outbox.append({"phone": phone, "code": code, "text": f"کد ورود شما: {code}"})

    def send_text(self, phone, text):
        self.outbox.append({"phone": phone, "code": None, "text": text})

    def send_event(self, phone, event, params, text):
        self.outbox.append({"phone": phone, "code": None, "text": text, "event": event, "params": params})


class SmsIrBackend(SmsBackend):
    """SMS.ir REST API v1. Codes go through an approved Verify template; texts need a line number."""

    base_url = "https://api.sms.ir/v1"

    def __init__(self):
        cfg = settings.SMSIR
        self.api_key = cfg.get("API_KEY", "")
        self.line_number = cfg.get("LINE_NUMBER", "")
        self.template_id = cfg.get("OTP_TEMPLATE_ID", 0)
        self.parameter = cfg.get("OTP_PARAMETER", "CODE")
        self.templates = cfg.get("TEMPLATES", {})

    def _client(self):
        import requests

        return requests

    def _post(self, path: str, payload: dict) -> dict:
        if not self.api_key:
            raise SmsError("SMSIR_API_KEY is not configured")
        try:
            resp = self._client().post(
                f"{self.base_url}{path}", json=payload, timeout=10,
                headers={"X-API-KEY": self.api_key, "Accept": "application/json"},
            )
            data = resp.json()
        except Exception as exc:  # network failure or a non-JSON body
            raise SmsError(f"SMS.ir request failed: {exc}") from exc
        if resp.status_code != 200 or data.get("status") != 1:
            raise SmsError(f"SMS.ir rejected the message ({resp.status_code}): {data.get('message')}")
        return data

    def send_otp(self, phone, code):
        if not self.template_id:
            # until a Verify template is approved, text the code from the line (development / trial
            # accounts; production requires the template, which also reaches numbers that block ads)
            if not self.line_number:
                raise SmsError("SMSIR_OTP_TEMPLATE_ID or SMSIR_LINE_NUMBER is not configured")
            self.send_text(phone, f"کد ورود شما: {code}")
            return
        self._post("/send/verify", {
            "mobile": phone,
            "templateId": int(self.template_id),
            "parameters": [{"name": self.parameter, "value": code}],
        })

    def send_text(self, phone, text):
        if not self.line_number:
            raise SmsError("SMSIR_LINE_NUMBER is not configured")
        self._post("/send/bulk", {"lineNumber": int(self.line_number), "messageText": text, "mobiles": [phone]})

    def send_event(self, phone, event, params, text):
        template_id = self.templates.get(event)
        if not template_id:
            self.send_text(phone, text)
            return
        self._post("/send/verify", {
            "mobile": phone,
            "templateId": int(template_id),
            "parameters": [
                {"name": name, "value": str(value).strip()[:PARAM_MAX_LENGTH]} for name, value in params.items()
            ],
        })


def get_backend() -> SmsBackend:
    module_path, _, class_name = settings.SMS_BACKEND.rpartition(".")
    return getattr(importlib.import_module(module_path), class_name)()


def notify(phone: str, text: str, *, event: str = "", params: dict | None = None) -> bool:
    """Best-effort notification: an SMS outage must never break the caller (e.g. placing an order).

    With an event, SMS.ir uses that event's Verify template (when configured) and `params`;
    `text` is what goes out otherwise.
    """
    if not phone:
        return False
    try:
        backend = get_backend()
        if event:
            backend.send_event(phone, event, params or {}, text)
        else:
            backend.send_text(phone, text)
    except SmsError as exc:
        logger.warning("SMS_NOTIFY_FAIL phone=%s error=%s", phone, exc)
        return False
    return True
