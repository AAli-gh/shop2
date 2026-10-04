"""The admin site: rate-limited sign-in and, with ADMIN_2FA_ENABLED, a second step by SMS code.

Step 1 checks the password but does not sign in; it texts a code to the staff member's
verified mobile. Step 2 checks the code, signs in and marks the session as admin-verified.
has_permission() requires that mark, so a staff account signed in on the storefront
(for example with a phone code alone) still has to pass both steps to reach the admin
or any staff page wrapped in admin.site.admin_view.
"""
from django.conf import settings
from django.contrib import admin, messages
from django.contrib.auth import REDIRECT_FIELD_NAME
from django.contrib.auth import login as auth_login
from django.contrib.auth.views import LoginView
from django.http import HttpResponseNotAllowed, HttpResponseRedirect
from django.shortcuts import redirect
from django.template.response import TemplateResponse
from django.urls import path, reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.csrf import csrf_protect

from apps.common.ratelimit import client_ip, ratelimit

SESSION_VERIFIED = "admin_2fa_user"
SESSION_PENDING = "admin_2fa_pending"
NO_VERIFIED_PHONE = (
    "ورود دومرحله‌ای فعال است، ولی این حساب شماره موبایل تأییدشده ندارد. "
    "ابتدا از پروفایل سایت شماره موبایل خود را ثبت و تأیید کنید."
)


def mask_phone(phone: str) -> str:
    return f"{phone[:4]}***{phone[-4:]}" if phone and len(phone) > 8 else phone


class AdminLoginView(LoginView):
    """Password step. Without 2FA it signs in as usual; with 2FA it texts the code instead."""

    def form_invalid(self, form):
        username = self.request.POST.get("username", "").strip()
        if username:
            from apps.common import shoplog

            shoplog.admin_login_failed(username, client_ip(self.request), step="password")
        return super().form_invalid(form)

    def form_valid(self, form):
        from apps.accounts.models import PhoneOTP
        from apps.accounts.views import _send_code
        from apps.common import shoplog

        user = form.get_user()
        if not settings.ADMIN_2FA_ENABLED:
            shoplog.admin_login(user, client_ip(self.request))
            return super().form_valid(form)

        if not (user.phone and user.phone_verified):
            form.add_error(None, NO_VERIFIED_PHONE)
            return super().form_invalid(form)
        error = _send_code(user.phone, PhoneOTP.Purpose.ADMIN, reuse_live_code=True)
        if error:
            form.add_error(None, error)
            return super().form_invalid(form)
        self.request.session[SESSION_PENDING] = {
            "user": user.pk,
            "backend": user.backend,
            "next": self.get_success_url(),
        }
        return redirect("admin:login_verify")


class ShopAdminSite(admin.AdminSite):
    # the shop's own right-hand menu (templates/admin/_shop_sidebar.html) replaces Django's app sidebar
    enable_nav_sidebar = False
    index_template = "admin/index.html"

    def each_context(self, request):
        context = super().each_context(request)
        if self.has_permission(request):
            from apps.common import admin_home

            context["shop_sidebar"] = admin_home.sidebar(request)
            context["shop_topbar"] = admin_home.topbar(request)
        return context

    def index(self, request, extra_context=None):
        from apps.common import admin_home

        days = request.GET.get("days", "30")
        days = int(days) if days in ("7", "30", "90") else 30
        return super().index(request, {**(extra_context or {}), "dash": admin_home.dashboard(request, days)})

    def search_view(self, request):
        from apps.common import admin_home

        q = request.GET.get("q", "")
        request.current_app = self.name
        return TemplateResponse(request, "admin/shop_search.html", {
            **self.each_context(request), "title": "جستجو", "q": q,
            "sections": admin_home.global_search(request, q),
        })

    def has_permission(self, request):
        if not super().has_permission(request):
            return False
        return not settings.ADMIN_2FA_ENABLED or request.session.get(SESSION_VERIFIED) == request.user.pk

    def get_urls(self):
        verify = ratelimit("admin_otp_verify", limit=20, window=600)(self.login_verify)
        resend = ratelimit("otp_request", limit=10, window=600)(self.login_resend)
        return [
            path("search/", self.admin_view(self.search_view), name="shop_search"),
            path("login/verify/", never_cache(csrf_protect(verify)), name="login_verify"),
            path("login/verify/resend/", never_cache(csrf_protect(resend)), name="login_resend"),
        ] + super().get_urls()

    def login(self, request, extra_context=None):
        if request.method == "GET" and self.has_permission(request):
            return HttpResponseRedirect(reverse("admin:index", current_app=self.name))

        from django.contrib.admin.forms import AdminAuthenticationForm

        context = {
            **self.each_context(request),
            "title": "ورود",
            "subtitle": None,
            "app_path": request.get_full_path(),
            "username": request.user.get_username(),
        }
        if REDIRECT_FIELD_NAME not in request.GET and REDIRECT_FIELD_NAME not in request.POST:
            context[REDIRECT_FIELD_NAME] = reverse("admin:index", current_app=self.name)
        context.update(extra_context or {})
        request.current_app = self.name
        view = AdminLoginView.as_view(
            extra_context=context,
            authentication_form=self.login_form or AdminAuthenticationForm,
            template_name=self.login_template or "admin/login.html",
        )
        # generous per IP (an office may share one), strict per account against password guessing
        return ratelimit("admin_login", limit=20, window=900, key_fields=("username",), key_limit=5)(view)(request)

    def _pending_user(self, request):
        from apps.accounts.models import User

        pending = request.session.get(SESSION_PENDING)
        if not (settings.ADMIN_2FA_ENABLED and pending):
            return None, None
        user = User.objects.filter(pk=pending["user"], is_active=True, is_staff=True).first()
        if user is None or not (user.phone and user.phone_verified):
            request.session.pop(SESSION_PENDING, None)
            return None, None
        return user, pending

    def login_verify(self, request):
        """Code step: sign in once the texted code matches."""
        from apps.accounts import otp
        from apps.accounts.forms import OtpCodeForm
        from apps.accounts.models import PhoneOTP
        from apps.common import shoplog

        user, pending = self._pending_user(request)
        if user is None:
            return redirect("admin:login")

        form = OtpCodeForm(request.POST or None)
        if request.method == "POST" and form.is_valid():
            try:
                otp.check_code(phone=user.phone, code=form.cleaned_data["code"], purpose=PhoneOTP.Purpose.ADMIN)
            except otp.OtpError as exc:
                form.add_error("code", str(exc))
                shoplog.admin_login_failed(user.get_username(), client_ip(request), step="sms")
            else:
                request.session.pop(SESSION_PENDING, None)
                auth_login(request, user, backend=pending["backend"])
                request.session[SESSION_VERIFIED] = user.pk
                shoplog.admin_login(user, client_ip(request))
                return HttpResponseRedirect(pending["next"] or reverse("admin:index", current_app=self.name))

        request.current_app = self.name
        return TemplateResponse(request, "admin/login_verify.html", {
            **self.each_context(request),
            "title": "کد تأیید ورود",
            "subtitle": None,
            "form": form,
            "masked_phone": mask_phone(user.phone),
            "otp_length": settings.OTP_LENGTH,
            "resend_in": otp.seconds_until_resend(user.phone, PhoneOTP.Purpose.ADMIN),
        })

    def login_resend(self, request):
        from apps.accounts.models import PhoneOTP
        from apps.accounts.views import _send_code

        if request.method != "POST":
            return HttpResponseNotAllowed(["POST"])
        user, _ = self._pending_user(request)
        if user is None:
            return redirect("admin:login")
        error = _send_code(user.phone, PhoneOTP.Purpose.ADMIN, reuse_live_code=False)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "کد جدید پیامک شد.")
        return redirect("admin:login_verify")
