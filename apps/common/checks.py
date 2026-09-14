from django.conf import settings
from django.core.checks import Tags, Warning, register


@register(Tags.security, deploy=True)
def admin_url_check(app_configs, **kwargs):
    """deploy.sh fails on warnings, so a production site can't keep the guessable /admin/ path."""
    if settings.ADMIN_URL.strip("/") == "admin":
        return [Warning(
            "The admin is served at the default /admin/ path, which bots probe for passwords.",
            hint="Set ADMIN_URL in .env to a hard-to-guess path, e.g. ADMIN_URL=panel-7fk2q/",
            id="shop.W001",
        )]
    return []
