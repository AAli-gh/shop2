from django.shortcuts import render

from apps.common.ratelimit import ratelimit
from apps.newsletter import services


@ratelimit("newsletter", limit=10, window=3600)
def subscribe(request):
    result = services.subscribe(email=request.POST.get("email", ""), user=request.user)
    if result["ok"]:
        from apps.common import shoplog

        shoplog.newsletter_subscribed(request.POST.get("email", ""))
    return render(
        request,
        "newsletter/partials/subscribe_result.html",
        {"ok": result["ok"], "message": result["message"]},
    )


def verify(request, token):
    verified = services.verify(token)
    return render(request, "newsletter/verify.html", {"verified": verified})


def unsubscribe(request, token):
    removed = services.unsubscribe(token)
    return render(request, "newsletter/unsubscribed.html", {"removed": removed})
