from django import forms

from apps.orders.models import ReturnRequest

MAX_RETURN_IMAGE_MB = 3


class ReturnRequestForm(forms.Form):
    """Reason and details; the items and quantities come as qty_<order item id> fields."""

    reason = forms.ChoiceField(label="دلیل مرجوعی", choices=ReturnRequest.Reason.choices, widget=forms.RadioSelect)
    resolution = forms.ChoiceField(
        label="درخواست شما", choices=ReturnRequest.Resolution.choices,
        initial=ReturnRequest.Resolution.REFUND, widget=forms.RadioSelect,
    )
    description = forms.CharField(
        label="توضیحات", min_length=10, max_length=2000,
        widget=forms.Textarea(attrs={
            "class": "input", "rows": 4, "placeholder": "مشکل کالا را توضیح دهید (مثلاً نوع ایراد یا آسیب)...",
        }),
    )
    image = forms.ImageField(label=f"عکس کالا (اختیاری، حداکثر {MAX_RETURN_IMAGE_MB} مگابایت)", required=False)

    def clean_image(self):
        image = self.cleaned_data.get("image")
        if image and image.size > MAX_RETURN_IMAGE_MB * 1024 * 1024:
            raise forms.ValidationError(f"حجم عکس حداکثر {MAX_RETURN_IMAGE_MB} مگابایت است.")
        return image
