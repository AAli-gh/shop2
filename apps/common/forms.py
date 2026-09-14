from django import forms

from apps.common.models import ContactMessage

INPUT = "input"


class ContactForm(forms.ModelForm):
    class Meta:
        model = ContactMessage
        fields = ["name", "email", "subject", "body"]
        widgets = {
            "name": forms.TextInput(attrs={"class": INPUT}),
            "email": forms.EmailInput(attrs={"class": INPUT}),
            "subject": forms.TextInput(attrs={"class": INPUT}),
            "body": forms.Textarea(attrs={"class": INPUT, "rows": 5}),
        }
