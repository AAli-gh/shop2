import pytest

from apps.common.models import SiteSettings, StaticPage


@pytest.mark.django_db
@pytest.mark.parametrize("url, title", [("/terms/", "قوانین و مقررات"), ("/privacy/", "حریم خصوصی")])
def test_legal_pages_exist_with_content(client, url, title):
    # seeded by migration so e-namad reviewers never hit a 404
    resp = client.get(url)
    body = resp.content.decode()
    assert resp.status_code == 200
    assert title in body
    assert "<h2" in body  # multi-line paragraphs render with headings


@pytest.mark.django_db
def test_footer_and_sign_in_link_to_legal_pages(client):
    home = client.get("/").content.decode()
    assert 'href="/terms/"' in home and 'href="/privacy/"' in home
    login = client.get("/accounts/login/").content.decode()
    assert 'href="/terms/"' in login


@pytest.mark.django_db
def test_trust_badges_render_only_when_configured(client):
    assert "trust-badges" not in client.get("/").content.decode()

    settings_obj = SiteSettings.load()
    settings_obj.trust_badges_html = (
        "<a referrerpolicy='origin' target='_blank' href='https://trustseal.enamad.ir/?id=1&Code=abc'>"
        "<img referrerpolicy='origin' src='https://trustseal.enamad.ir/logo.aspx?id=1&Code=abc' alt='' id='abc'></a>"
    )
    settings_obj.save()

    home = client.get("/").content.decode()
    assert "trust-badges" in home
    assert "https://trustseal.enamad.ir/logo.aspx?id=1&Code=abc" in home  # the official snippet, unescaped


@pytest.mark.django_db
def test_editing_a_legal_page_in_admin_shows_on_site(client):
    page = StaticPage.objects.get(key="terms")
    page.body = "بند تازه\nمتن این بند."
    page.save()
    body = client.get("/terms/").content.decode()
    assert "بند تازه" in body and "متن این بند." in body
