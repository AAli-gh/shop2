import pytest

from apps.newsletter.models import Campaign


@pytest.mark.django_db
def test_preview_of_missing_campaign_is_404(admin_client):
    assert admin_client.get("/admin/newsletter/campaign/999999/preview/").status_code == 404


@pytest.mark.django_db
def test_preview_needs_campaign_permission(client, django_user_model):
    campaign = Campaign.objects.create(subject="تخفیف", body="متن")
    staff = django_user_model.objects.create_user(email="clerk@example.com", password="x", is_staff=True)
    client.force_login(staff)
    assert client.get(f"/admin/newsletter/campaign/{campaign.pk}/preview/").status_code == 403
