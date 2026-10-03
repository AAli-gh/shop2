from django import forms
from django.contrib.auth.forms import (
    AuthenticationForm,
    PasswordChangeForm,
    PasswordResetForm,
    SetPasswordForm,
    UserCreationForm,
)

from apps.accounts.models import Address, User

INPUT = "input"


class RegisterForm(UserCreationForm):
    name = forms.CharField(
        label="نام و نام خانوادگی", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": INPUT}),
    )

    class Meta:
        model = User
        fields = ("email", "name")
        widgets = {
            "email": forms.EmailInput(attrs={"class": INPUT}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["password1"].widget.attrs.update({"class": INPUT})
        self.fields["password2"].widget.attrs.update({"class": INPUT})


class EmailAuthenticationForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "ایمیل"
        self.fields["username"].widget.attrs.update({"class": INPUT, "type": "email"})
        self.fields["password"].widget.attrs.update({"class": INPUT})


class ResendVerificationForm(forms.Form):
    email = forms.EmailField(
        label="ایمیل", widget=forms.EmailInput(attrs={"class": INPUT})
    )


class StyledPasswordResetForm(PasswordResetForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].widget.attrs.update({"class": INPUT})

    def get_email_field_name(self):
        return "email"


class StyledSetPasswordForm(SetPasswordForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["new_password1"].widget.attrs.update({"class": INPUT})
        self.fields["new_password2"].widget.attrs.update({"class": INPUT})


class StyledPasswordChangeForm(PasswordChangeForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ("old_password", "new_password1", "new_password2"):
            self.fields[name].widget.attrs.update({"class": INPUT})


class ProfileForm(forms.Form):
    # the phone number is a login identity, so it only changes through SMS verification
    name = forms.CharField(
        label="نام و نام خانوادگی", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    accepts_marketing = forms.BooleanField(
        label="کد تخفیف و پیشنهادهای ویژه را برایم پیامک یا ایمیل کنید", required=False,
        widget=forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
    )


class PhoneForm(forms.Form):
    phone = forms.CharField(
        label="شماره موبایل", max_length=20,
        widget=forms.TextInput(attrs={
            "class": INPUT, "dir": "ltr", "inputmode": "tel", "autocomplete": "tel",
            "placeholder": "09123456789", "autofocus": True,
        }),
    )

    def clean_phone(self):
        from apps.accounts.otp import normalize_phone

        phone = normalize_phone(self.cleaned_data["phone"])
        if phone is None:
            raise forms.ValidationError("شماره موبایل معتبر نیست (مثلاً ۰۹۱۲۳۴۵۶۷۸۹).")
        return phone


class OtpCodeForm(forms.Form):
    code = forms.CharField(
        label="کد تأیید", max_length=10,
        widget=forms.TextInput(attrs={
            "class": INPUT + " text-center text-lg font-bold tracking-[0.5em]", "dir": "ltr",
            "inputmode": "numeric", "autocomplete": "one-time-code", "autofocus": True,
        }),
    )


class AddressForm(forms.ModelForm):
    class Meta:
        model = Address
        fields = ["full_name", "phone", "province", "city", "postal_code", "address_line", "is_default"]
        widgets = {
            "full_name": forms.TextInput(attrs={"class": INPUT}),
            "phone": forms.TextInput(attrs={"class": INPUT, "dir": "ltr"}),
            "province": forms.TextInput(attrs={"class": INPUT}),
            "city": forms.TextInput(attrs={"class": INPUT}),
            "postal_code": forms.TextInput(attrs={"class": INPUT, "dir": "ltr", "inputmode": "numeric"}),
            "address_line": forms.Textarea(attrs={"class": INPUT, "rows": 3}),
            "is_default": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }
