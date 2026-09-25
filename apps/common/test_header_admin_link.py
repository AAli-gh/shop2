import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_staff_see_a_button_to_the_admin(client, django_user_model):
    staff = django_user_model.objects.create_user(email="manager@example.com", password="x", is_staff=True)
    client.force_login(staff)

    page = client.get("/").content.decode()

    assert "data-admin-link" in page
    assert f'href="{reverse("admin:index")}"' in page


@pytest.mark.django_db
@pytest.mark.parametrize("signed_in", [False, True])
def test_customers_and_guests_never_see_the_admin_address(client, django_user_model, settings, signed_in):
    if signed_in:
        client.force_login(django_user_model.objects.create_user(email="buyer@example.com", password="x"))

    page = client.get("/").content.decode()

    assert "data-admin-link" not in page
    assert reverse("admin:index") not in page
