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
    name = forms.CharField(
        label="نام و نام خانوادگی", max_length=120, required=False,
        widget=forms.TextInput(attrs={"class": INPUT}),
    )
    phone = forms.CharField(
        label="شماره موبایل", max_length=15, required=False,
        widget=forms.TextInput(attrs={"class": INPUT, "dir": "ltr"}),
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
