from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.common.ratelimit import ratelimit
from apps.common.services import get_settings
from apps.loyalty import services
from apps.loyalty.services import LoyaltyError


@login_required
def club_page(request):
    if not services.is_enabled():
        raise Http404("باشگاه مشتریان فعال نیست")
    account = services.get_account(request.user)
    settings_obj = get_settings()
    referrals = request.user.referrals.all()  # club accounts of the customers this one brought in
    return render(request, "loyalty/club.html", {
        "account": account,
        "club": settings_obj,
        "points_value": max(account.points, 0) * settings_obj.loyalty_point_value,
        "can_redeem": account.points >= settings_obj.loyalty_min_redeem_points,
        "share_url": request.build_absolute_uri(f"/?ref={account.referral_code}"),
        "referral_count": referrals.count(),
        "rewarded_count": referrals.filter(referral_rewarded=True).count(),
        "can_enter_code": services.can_enter_referral_code(request.user),
        "transactions": account.transactions.select_related("order")[:30],
    })


@login_required
@require_POST
def redeem(request):
    try:
        points = int(request.POST.get("points", ""))
    except (TypeError, ValueError):
        points = 0
    try:
        amount = services.redeem(user=request.user, points=points)
    except LoyaltyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, f"{amount:,} تومان به کیف پول شما اضافه شد.")
    return redirect("loyalty:club")


@login_required
@require_POST
@ratelimit("referral_code", limit=10, window=3600)  # codes are guessable, like gift codes
def enter_code(request):
    try:
        services.set_referrer(user=request.user, code=request.POST.get("code", ""))
    except LoyaltyError as exc:
        messages.error(request, str(exc))
    else:
        messages.success(request, "کد معرف ثبت شد؛ پس از تحویل اولین خریدتان، هدیه‌اش به شما و دوستتان می‌رسد.")
    return redirect("loyalty:club")
