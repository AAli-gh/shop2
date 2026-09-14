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


@ratelimit("contact", limit=5, window=3600)
def contact(request):
    if request.method == "POST":
        form = ContactForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "پیام شما ثبت شد. به‌زودی پاسخ می‌دهیم.")
            return redirect("common:contact")
    else:
        initial = {"email": request.user.email} if request.user.is_authenticated else {}
        form = ContactForm(initial=initial)
    return render(
        request, "pages/contact.html", {"form": form, "settings_obj": get_settings()}
    )
