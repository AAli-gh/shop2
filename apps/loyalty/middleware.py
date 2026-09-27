from apps.loyalty import services


class ReferralMiddleware:
    """Any page opened from a shared link (?ref=CODE) remembers the code for the sign-up that follows."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if "ref" in request.GET:
            services.remember_referral(request)
        return self.get_response(request)
