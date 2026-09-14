from django.contrib import admin, messages
from django.shortcuts import render
from django.utils import timezone
from django.urls import path

from apps.common.admin_jalali import jalali_column
from apps.newsletter.models import Campaign, Subscriber
from apps.newsletter.services import send_campaign, verified_emails


@admin.register(Subscriber)
class SubscriberAdmin(admin.ModelAdmin):
    list_display = ("email", "name", "is_verified", "created_jalali")
    list_filter = ("is_verified",)
    search_fields = ("email", "name")
    readonly_fields = ("unsub_token", "verify_token", "created_jalali")

    created_jalali = jalali_column("created_at", "تاریخ عضویت")
    actions = ["export_emails"]

    @admin.action(description="کپی ایمیل‌های انتخاب‌شده (نمایش در پیام)")
    def export_emails(self, request, queryset):
        emails = ", ".join(queryset.values_list("email", flat=True))
        self.message_user(request, emails[:4000])


@admin.register(Campaign)
class CampaignAdmin(admin.ModelAdmin):
    list_display = ("subject", "status", "sent_count", "sent_jalali", "created_jalali", "preview_link")
    readonly_fields = ("status", "sent_count", "sent_jalali", "created_jalali")
    actions = ["send_now"]

    sent_jalali = jalali_column("sent_at", "زمان ارسال")
    created_jalali = jalali_column("created_at", "تاریخ ساخت")

    @admin.display(description="پیش‌نمایش")
    def preview_link(self, obj):
        from django.utils.html import format_html

        return format_html('<a class="button" href="{}preview/">ایمیل</a>', obj.pk)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "<int:pk>/preview/",
                self.admin_site.admin_view(self.preview),
                name="newsletter_campaign_preview",
            ),
        ]
        return custom + urls

    def preview(self, request, pk):
        campaign = Campaign.objects.get(pk=pk)
        return render(
            request,
            "admin/newsletter/campaign_preview.html",
            {"campaign": campaign, "opts": self.model._meta},
        )

    @admin.action(description="ارسال فوری به مشترکین تأییدشده")
    def send_now(self, request, queryset):
        total = 0
        for campaign in queryset.filter(status=Campaign.Status.DRAFT):
            total += send_campaign(campaign)
        messages.success(request, f"کمپین به {total} مشترک ارسال شد.")
