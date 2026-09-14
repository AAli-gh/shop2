from django.contrib import messages
from django.contrib.auth import login as auth_login
from django.contrib.auth import views as auth_views
from django.contrib.auth.mixins import LoginRequiredMixin
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse_lazy
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import (
    CreateView,
    DeleteView,
    FormView,
    ListView,
    TemplateView,
    UpdateView,
)

from apps.accounts import services
from apps.accounts.forms import (
    AddressForm,
    EmailAuthenticationForm,
    ProfileForm,
    RegisterForm,
    ResendVerificationForm,
    StyledPasswordChangeForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
)
from apps.accounts.models import Address, User
from apps.common.ratelimit import ratelimit


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
        services.register_user(
            email=form.cleaned_data["email"],
            password=form.cleaned_data["password1"],
            name=form.cleaned_data["name"],
        )
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


# generous per IP (mobile carriers share IPs), strict per account against password guessing
@method_decorator(ratelimit("login", limit=20, window=600, key_fields=("username",), key_limit=8), name="dispatch")
class LoginView(auth_views.LoginView):
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
        return {"name": self.request.user.name, "phone": self.request.user.phone}

    def form_valid(self, form):
        services.update_profile(
            user=self.request.user,
            name=form.cleaned_data["name"],
            phone=form.cleaned_data["phone"],
        )
        messages.success(self.request, "پروفایل به‌روزرسانی شد.")
        return super().form_valid(form)


class PasswordChangeView(auth_views.PasswordChangeView):
    template_name = "accounts/password_change.html"
    form_class = StyledPasswordChangeForm
    success_url = reverse_lazy("accounts:profile")

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
