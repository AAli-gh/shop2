from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from apps.common.ratelimit import ratelimit
from apps.wallet import services
from apps.wallet.models import WalletTransaction
from apps.wallet.services import WalletError


@login_required
def wallet_page(request):
    wallet = services.get_wallet(request.user)
    return render(
        request,
        "wallet/wallet.html",
        {"wallet": wallet, "transactions": wallet.transactions.all()[:20]},
    )


@login_required
@ratelimit("gift_card", limit=5, window=600)  # gift codes are guessable secrets
def redeem_code(request):
    if request.method == "POST":
        try:
            result = services.redeem_gift_card(user=request.user, code=request.POST.get("code", ""))
            messages.success(
                request, f"{result['amount']:,} تومان به کیف پول شما اضافه شد."
            )
        except WalletError as exc:
            messages.error(request, str(exc))
    return redirect("wallet:page")
