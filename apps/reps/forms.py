from django import forms

from apps.orders.models import Order
from apps.reps.models import RepCustomer

INPUT = "input"


class RepCustomerForm(forms.ModelForm):
    class Meta:
        model = RepCustomer
        fields = ["shop_name", "owner_name", "phone", "province", "city", "address", "postal_code", "notes", "is_active"]
        widgets = {
            "shop_name": forms.TextInput(attrs={"class": INPUT}),
            "owner_name": forms.TextInput(attrs={"class": INPUT}),
            "phone": forms.TextInput(attrs={"class": INPUT, "dir": "ltr", "inputmode": "tel"}),
            "province": forms.TextInput(attrs={"class": INPUT}),
            "city": forms.TextInput(attrs={"class": INPUT}),
            "address": forms.Textarea(attrs={"class": INPUT, "rows": 2}),
            "postal_code": forms.TextInput(attrs={"class": INPUT, "dir": "ltr", "inputmode": "numeric"}),
            "notes": forms.TextInput(attrs={"class": INPUT}),
            "is_active": forms.CheckboxInput(attrs={"class": "h-4 w-4"}),
        }


class PlaceOrderForm(forms.Form):
    customer = forms.ModelChoiceField(
        queryset=RepCustomer.objects.none(), label="مشتری", empty_label="یک مشتری انتخاب کنید",
        widget=forms.Select(attrs={"class": INPUT}),
    )
    payment_terms = forms.ChoiceField(
        choices=Order.PaymentTerms.choices, label="نحوه پرداخت", widget=forms.Select(attrs={"class": INPUT}),
    )
    note = forms.CharField(
        label="توضیح برای انبار و ارسال", required=False, max_length=200,
        widget=forms.TextInput(attrs={"class": INPUT, "placeholder": "مثلاً تحویل تا ظهر پنجشنبه"}),
    )

    def __init__(self, *args, rep, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["customer"].queryset = rep.customers.filter(is_active=True)
