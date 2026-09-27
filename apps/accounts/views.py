from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.utils.decorators import method_decorator
from django.utils.http import url_has_allowed_host_and_scheme
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts import otp, services
from apps.accounts.forms import (
    AddressForm,
    EmailAuthenticationForm,
    OtpCodeForm,
    PhoneForm,
    ProfileForm,
    RegisterForm,
    ResendVerificationForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from apps.accounts.models import Address, PhoneOTP, User
from apps.common.ratelimit import is_limited, ratelimit


@method_decorator(ratelimit("password_reset", limit=5, window=3600, key_fields=("email",)), name="dispatch")
class PasswordResetView(auth_views.PasswordResetView):
    form_class = StyledPasswordResetForm
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.html"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


@method_decorator(ratelimit("register", limit=5, window=3600), name="dispatch")
class RegisterView(FormView):
    template_name = "accounts/register.html"
    form_class = RegisterForm
    success_url = reverse_lazy("accounts:verification_sent")

    def form_valid(self, form):
        user = services.register_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password1"],
            name=form.cleaned_data["name"],
        )
        from apps.loyalty.services import attach_referral_from_session

        attach_referral_from_session(self.request, user)
        messages.success(self.request, "ثبت‌نام انجام شد؛ لطفاً ایمیل خود را برای تأیید بررسی کنید.")
        return super().form_valid(form)


class VerificationSentView(TemplateView):
    template_name = "accounts/verification_sent.html"


class VerifyEmailView(View):
    def get(self, request, token):
        verified = services.verify_token(token)
        return render(
            request,
            "accounts/verify_email.html",
            {"verified": verified},
        )


@method_decorator(ratelimit("resend_verification", limit=5, window=3600, key_fields=("email",)), name="dispatch")
class ResendVerificationView(FormView):
    template_name = "accounts/resend_verification.html"
    form_class = ResendVerificationForm
    success_url = reverse_lazy("accounts:verification_sent")

    def form_valid(self, form):
        user = User.objects.filter(email=form.cleaned_data["email"], is_active=False).first()
        if user:
            services.send_verification_email(user)
        messages.success(self.request, "اگر حساب تأییدنشده‌ای با این ایمیل دارید، لینک جدید ارسال شد.")
        return super().form_valid(form)


SESSION_LOGIN_PHONE = "otp_login_phone"
SESSION_LOGIN_NEXT = "otp_login_next"
SESSION_CHANGE_PHONE = "otp_change_phone"
TOO_MANY_CODES = "برای این شماره کد زیادی درخواست شده؛ چند دقیقه بعد دوباره تلاش کنید."


def _safe_next(request, value: str) -> str:
    if value and url_has_allowed_host_and_scheme(
        value, allowed_hosts={request.get_host()}, require_https=request.is_secure()
    ):
        return value
    return ""


def _send_code(phone: str, purpose: str, *, reuse_live_code: bool) -> str:
    """Text a code to phone; return an error message, or "" on success.

    With reuse_live_code, a code sent moments ago is kept instead of texting another
    (e.g. the customer pressed back and submitted the same number again).
    """
    if reuse_live_code and otp.seconds_until_resend(phone, purpose) and otp.has_live_code(phone, purpose):
        return ""
    # normalized number, so "+98..." and "09..." share one counter
    if is_limited(f"otp_phone:{purpose}", phone, limit=3, window=600):
        return TOO_MANY_CODES
    try:
        otp.request_code(phone=phone, purpose=purpose)
    except otp.OtpError as exc:
        return str(exc)
    return ""


def _verify_context(phone: str, purpose: str, resend_url: str, change_url: str) -> dict:
    return {
        "phone": phone,
        "otp_length": settings.OTP_LENGTH,
        "resend_in": otp.seconds_until_resend(phone, purpose),
        "resend_url": resend_url,
        "change_url": change_url,
    }


@method_decorator(ratelimit("otp_request", limit=10, window=600), name="dispatch")
class PhoneLoginView(FormView):
    """Sign in or sign up, step 1: take a mobile number and text it a code."""

    template_name = "accounts/login_phone.html"
    form_class = PhoneForm

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect(_safe_next(request, request.GET.get("next", "")) or "/")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["next"] = _safe_next(self.request, self.request.GET.get("next", ""))
        return context

    def form_valid(self, form):
        phone = form.cleaned_data["phone"]
        error = _send_code(phone, PhoneOTP.Purpose.LOGIN, reuse_live_code=True)
        if error:
            form.add_error("phone", error)
            return self.form_invalid(form)
        self.request.session[SESSION_LOGIN_PHONE] = phone
        self.request.session[SESSION_LOGIN_NEXT] = _safe_next(self.request, self.request.POST.get("next", ""))
        return redirect("accounts:login_verify")


@method_decorator(ratelimit("otp_verify", limit=30, window=600), name="dispatch")
class PhoneLoginVerifyView(FormView):
    """Step 2: check the code, then sign in (creating the account on first login)."""

    template_name = "accounts/login_verify.html"
    form_class = OtpCodeForm

    def dispatch(self, request, *args, **kwargs):
        self.phone = request.session.get(SESSION_LOGIN_PHONE)
        if not self.phone:
            return redirect("accounts:login")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_verify_context(
            self.phone, PhoneOTP.Purpose.LOGIN, reverse("accounts:login_resend"), reverse("accounts:login"),
        ))
        return context

    def form_valid(self, form):
        try:
            user, created = otp.login_with_code(phone=self.phone, code=form.cleaned_data["code"])
        except otp.OtpError as exc:
            form.add_error("code", str(exc))
            return self.form_invalid(form)

        next_url = self.request.session.pop(SESSION_LOGIN_NEXT, "")
        self.request.session.pop(SESSION_LOGIN_PHONE, None)
        auth_login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        from apps.cart import services as cart_services

        cart_services.merge_carts(self.request, user)
        if created:
            from apps.loyalty.services import attach_referral_from_session

            attach_referral_from_session(self.request, user)
            messages.success(self.request, "حساب شما ساخته شد؛ خوش آمدید! نام خود را در پروفایل کامل کنید.")
            return redirect(next_url or "accounts:profile")
        messages.success(self.request, "خوش آمدید!")
        return redirect(next_url or "/")


@method_decorator(ratelimit("otp_request", limit=10, window=600), name="dispatch")
class PhoneLoginResendView(View):
    def post(self, request):
        phone = request.session.get(SESSION_LOGIN_PHONE)
        if not phone:
            return redirect("accounts:login")
        error = _send_code(phone, PhoneOTP.Purpose.LOGIN, reuse_live_code=False)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "کد جدید پیامک شد.")
        return redirect("accounts:login_verify")


@method_decorator(ratelimit("otp_request", limit=10, window=600), name="dispatch")
class PhoneChangeView(LoginRequiredMixin, FormView):
    """Add or replace the account's mobile number (step 1)."""

    template_name = "accounts/phone_change.html"
    form_class = PhoneForm

    def form_valid(self, form):
        user = self.request.user
        phone = form.cleaned_data["phone"]
        if phone == user.phone and user.phone_verified:
            form.add_error("phone", "این شماره همین حالا روی حساب شماست.")
            return self.form_invalid(form)
        if User.objects.filter(phone=phone, phone_verified=True).exclude(pk=user.pk).exists():
            form.add_error("phone", "این شماره به حساب دیگری متصل است.")
            return self.form_invalid(form)
        error = _send_code(phone, PhoneOTP.Purpose.CHANGE_PHONE, reuse_live_code=True)
        if error:
            form.add_error("phone", error)
            return self.form_invalid(form)
        self.request.session[SESSION_CHANGE_PHONE] = phone
        return redirect("accounts:phone_change_verify")


@method_decorator(ratelimit("otp_verify", limit=30, window=600), name="dispatch")
class PhoneChangeVerifyView(LoginRequiredMixin, FormView):
    template_name = "accounts/phone_change_verify.html"
    form_class = OtpCodeForm

    def dispatch(self, request, *args, **kwargs):
        self.phone = request.session.get(SESSION_CHANGE_PHONE)
        if request.user.is_authenticated and not self.phone:
            return redirect("accounts:phone_change")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context.update(_verify_context(
            self.phone, PhoneOTP.Purpose.CHANGE_PHONE,
            reverse("accounts:phone_change_resend"), reverse("accounts:phone_change"),
        ))
        return context

    def form_valid(self, form):
        try:
            otp.change_phone_with_code(user=self.request.user, phone=self.phone, code=form.cleaned_data["code"])
        except otp.OtpError as exc:
            form.add_error("code", str(exc))
            return self.form_invalid(form)
        self.request.session.pop(SESSION_CHANGE_PHONE, None)
        messages.success(self.request, "شماره موبایل شما ثبت شد.")
        return redirect("accounts:profile")


@method_decorator(ratelimit("otp_request", limit=10, window=600), name="dispatch")
class PhoneChangeResendView(LoginRequiredMixin, View):
    def post(self, request):
        phone = request.session.get(SESSION_CHANGE_PHONE)
        if not phone:
            return redirect("accounts:phone_change")
        error = _send_code(phone, PhoneOTP.Purpose.CHANGE_PHONE, reuse_live_code=False)
        if error:
            messages.error(request, error)
        else:
            messages.success(request, "کد جدید پیامک شد.")
        return redirect("accounts:phone_change_verify")


# generous per IP (mobile carriers share IPs), strict per account against password guessing
@method_decorator(ratelimit("login", limit=20, window=600, key_fields=("username",), key_limit=8), name="dispatch")
class EmailLoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    form_class = EmailAuthenticationForm
    redirect_authenticated_user = True

    def form_invalid(self, form):
        # friendlier message for unverified (inactive) accounts
        email = self.request.POST.get("username", "").strip().lower()
        if email and form.non_field_errors():
            from apps.accounts.models import User as UserModel

            if UserModel.objects.filter(email=email, is_active=False, email_verified=False).exists():
                messages.error(self.request, "حساب شما هنوز تأیید نشده است. لطفاً ایمیل تأیید را بررسی کنید.")
        return super().form_invalid(form)

    def form_valid(self, form):
        response = super().form_valid(form)
        from apps.cart import services as cart_services

        cart_services.merge_carts(self.request, self.request.user)
        return response


class LogoutView(auth_views.LogoutView):
    pass


class ProfileView(LoginRequiredMixin, FormView):
    template_name = "accounts/profile.html"
    form_class = ProfileForm
    success_url = reverse_lazy("accounts:profile")

    def get_initial(self):
        return {"name": self.request.user.name}

    def form_valid(self, form):
        services.update_profile(user=self.request.user, name=form.cleaned_data["name"])
        messages.success(self.request, "پروفایل به‌روزرسانی شد.")
        return super().form_valid(form)


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

    def get_form_class(self):
        # accounts created by SMS login have no password yet, so there is no "old password" to ask for
        if not self.request.user.has_usable_password():
            return StyledSetPasswordForm
        return super().get_form_class()

    def form_valid(self, form):
        messages.success(self.request, "گذرواژه با موفقیت تغییر کرد.")
        return super().form_valid(form)


class AddressListView(LoginRequiredMixin, ListView):
    template_name = "accounts/address_list.html"
    context_object_name = "addresses"

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)


class AddressCreateView(LoginRequiredMixin, CreateView):
    template_name = "accounts/address_form.html"
    form_class = AddressForm
    success_url = reverse_lazy("accounts:address_list")

    def form_valid(self, form):
        services.create_address(user=self.request.user, **form.cleaned_data)
        messages.success(self.request, "آدرس ثبت شد.")
        return redirect(self.success_url)


class AddressUpdateView(LoginRequiredMixin, UpdateView):
    template_name = "accounts/address_form.html"
    form_class = AddressForm
    success_url = reverse_lazy("accounts:address_list")

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def form_valid(self, form):
        services.update_address(address=self.object, **form.cleaned_data)
        messages.success(self.request, "آدرس به‌روزرسانی شد.")
        return redirect(self.success_url)


class AddressDeleteView(LoginRequiredMixin, DeleteView):
    model = Address
    success_url = reverse_lazy("accounts:address_list")

    def get_queryset(self):
        return Address.objects.filter(user=self.request.user)

    def post(self, request, *args, **kwargs):
        services.delete_address(user=request.user, address_id=kwargs["pk"])
        messages.success(request, "آدرس حذف شد.")
        return redirect(self.success_url)


class AddressSetDefaultView(LoginRequiredMixin, View):
    def post(self, request, pk):
        address = get_object_or_404(Address, pk=pk, user=request.user)
        services.set_default_address(user=request.user, address_id=address.pk)
        return redirect("accounts:address_list")
