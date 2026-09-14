import re

from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.utils import timezone

from apps.newsletter.models import Campaign, Subscriber

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def subscribe(*, email: str, user=None) -> dict:
    email = (email or "").strip().lower()
    if not EMAIL_RE.match(email):
        return {"ok": False, "message": "ایمیل معتبر وارد کنید."}

    subscriber, created = Subscriber.objects.get_or_create(
        email=email,
        defaults={"user": user if getattr(user, "is_authenticated", False) else None},
    )
    if subscriber.is_verified:
        return {"ok": True, "message": "شما قبلاً عضو خبرنامه شده‌اید."}

    from django.urls import reverse

    link = settings.SITE_URL + reverse("newsletter:verify", kwargs={"token": subscriber.verify_token})
    body = render_to_string(
        "newsletter/emails/confirm.txt",
        {"link": link},
    )
    send_mail_fallback(
        subject="تأیید عضویت در خبرنامه",
        body=body,
        to=[email],
    )
    return {"ok": True, "message": "ایمیل تأیید برایتان ارسال شد؛ روی لینک داخل آن کلیک کنید."}


def send_mail_fallback(*, subject: str, body: str, to: list) -> None:
    send_mail_raw(subject=subject, body=body, to=to)


def send_mail_raw(*, subject: str, body: str, to: list) -> None:
    from django.core.mail import send_mail

    send_mail(subject, body, settings.DEFAULT_FROM_EMAIL, to, fail_silently=True)


def verify(token: str) -> bool:
    sub = Subscriber.objects.filter(verify_token=token).first()
    if not sub:
        return False
    sub.is_verified = True
    sub.verify_token = ""
    sub.save(update_fields=["is_verified", "verify_token"])
    return True


def unsubscribe(token: str) -> bool:
    sub = Subscriber.objects.filter(unsub_token=token).first()
    if not sub:
        return False
    sub.delete()
    return True


def verified_emails() -> list:
    return list(Subscriber.objects.filter(is_verified=True).values_list("email", flat=True))


def send_campaign(campaign: Campaign) -> int:
    """Send to all verified subscribers; marks campaign sent. Returns count."""
    if campaign.status == Campaign.Status.SENT:
        return 0
    emails = verified_emails()
    link_unsub_base = settings.SITE_URL + "/newsletter/unsubscribe/"
    sent = 0
    for email in emails:
        sub = Subscriber.objects.filter(email=email).first()
        body = render_to_string(
            "newsletter/emails/campaign.txt",
            {"campaign": campaign, "store": settings.SITE_STORE_NAME, "unsub_link": link_unsub_base + (sub.unsub_token if sub else "")},
        )
        try:
            send_mail_raw(subject=campaign.subject, body=body, to=[email])
            sent += 1
        except Exception:
            continue
    campaign.status = Campaign.Status.SENT
    campaign.sent_count = sent
    campaign.sent_at = timezone.now()
    campaign.save(update_fields=["status", "sent_count", "sent_at"])
    return sent
