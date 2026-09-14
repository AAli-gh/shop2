import re

from apps.catalog.models import RestockNotification

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def subscribe(*, product, email: str) -> dict:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "message": "ایمیل معتبر وارد کنید."}
    obj, created = RestockNotification.objects.get_or_create(product=product, email=email)
    if not created and obj.notified:
        obj.notified = False
        obj.save(update_fields=["notified"])
    return {"ok": True, "message": "ثبت شد؛ به‌محض موجود شدن خبرتان می‌کنیم."}
