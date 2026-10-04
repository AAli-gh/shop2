from django.contrib import messages
from django.http import Http404
from django.shortcuts import redirect, render

from apps.common.forms import ContactForm
from apps.common.models import StaticPage
from apps.common.ratelimit import ratelimit
from apps.common.services import get_settings


def about(request):
    return render(request, "pages/about.html")


def static_page(request, key):
    page = StaticPage.objects.filter(key=key).first()
    if page is None:
        raise Http404("صفحه یافت نشد")
    return render(request, "pages/static_page.html", {"page": page})


def _email_contact_message(message) -> None:
    """Forward a contact message to the shop (settings.ADMINS); «Reply» in the mail client answers the customer.

    The message is already saved, so a mail outage only loses the copy, never the message.
    """
    from django.conf import settings
    from django.core.mail import EmailMessage
    from django.urls import reverse

    recipients = [email for _, email in settings.ADMINS if email]
    if not recipients:
        return
    subject = " ".join(message.subject.split())  # one line: a header can't be split by what the visitor typed
    link = settings.SITE_URL.rstrip("/") + reverse("admin:common_contactmessage_change", args=[message.pk])
    body = f"از: {message.name} <{message.email}>\nموضوع: {subject}\n\n{message.body}\n\nدر پنل مدیریت: {link}"
    EmailMessage(
        f"پیام تماس: {subject}"[:200], body, settings.DEFAULT_FROM_EMAIL, recipients, reply_to=[message.email],
    ).send(fail_silently=True)


@ratelimit("contact", limit=5, window=3600)
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            _email_contact_message(form.save())
            messages.success(request, "پیام شما ثبت شد. به‌زودی پاسخ می‌دهیم.")
            return redirect("common:contact")
    else:
        initial = {"email": request.user.email or ""} if request.user.is_authenticated else {}
        form = ContactForm(initial=initial)
    return render(
        request, "pages/contact.html", {"form": form, "settings_obj": get_settings()}
    )
