from django.contrib import admin, messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.orders import returns, services
from apps.orders.forms import ReturnRequestForm
from apps.orders.models import Order, ReturnRequest
from apps.orders.services import OrderError
from apps.common.ratelimit import ratelimit
from apps.payments.gateways import get_gateway
from apps.payments.models import Payment
from apps.payments.services import PaymentError, complete_payment, start_payment


class CheckoutView(LoginRequiredMixin, TemplateView):
    template_name = "orders/checkout.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        cart = cart_services.get_or_create_cart(self.request)
        summary = cart_services.cart_summary(cart)
        coupon_code = self.request.session.get("coupon_code", "")
        coupon_result = None
        if coupon_code:
            from apps.discounts import services as discount_services

            coupon_result = discount_services.validate_coupon(
                code=coupon_code, subtotal=summary["subtotal"], user=self.request.user
            )
            if coupon_result.error:
                coupon_code = ""
                self.request.session.pop("coupon_code", None)
        from apps.orders.models import ShippingMethod

        context["summary"] = summary
        context["shipping_methods"] = ShippingMethod.objects.filter(is_active=True)
        context["needs_install"] = any(
            item["product"].requires_install for item in summary["items"]
        )
        context["totals"] = services.checkout_context_data(
            self.request.user, summary, coupon_result, install_needed=context["needs_install"]
        )
        context["coupon_code"] = coupon_code
        context["addresses"] = Address.objects.filter(user=self.request.user)
        return context


@method_decorator(ratelimit("coupon", limit=15, window=600), name="dispatch")
class CouponApplyView(LoginRequiredMixin, View):
    def post(self, request):
        from apps.discounts import services as discount_services

        cart = cart_services.get_or_create_cart(request)
        summary = cart_services.cart_summary(cart)
        code = request.POST.get("code", "")
        result = services.apply_coupon_to_session(request, code=code, subtotal=summary["subtotal"])
        totals = services.checkout_context_data(request.user, summary, result if not result.error else None)
        return render(
            request,
            "orders/partials/checkout_summary.html",
            {
                "summary": summary,
                "totals": totals,
                "coupon_result": result,
                "coupon_code": request.session.get("coupon_code", ""),
                "error_message": discount_services.error_message(result.error) if result.error else "",
            },
        )


ADDRESS_FIELDS = ("full_name", "phone", "province", "city", "postal_code", "address_line")


def _posted_id(request, name: str) -> int | None:
    value = (request.POST.get(name) or "").strip()
    return int(value) if value.isdigit() else None


class PlaceOrderView(LoginRequiredMixin, View):
    def post(self, request):
        from apps.accounts.forms import AddressForm

        cart = cart_services.get_or_create_cart(request)
        save_address = False

        if request.POST.get("address_id"):
            address = get_object_or_404(Address, pk=_posted_id(request, "address_id"), user=request.user)
            address_data = {field: getattr(address, field) for field in ADDRESS_FIELDS}
        else:
            # same rules as the address book: required fields, lengths the columns can hold
            form = AddressForm({field: request.POST.get(field, "").strip() for field in ADDRESS_FIELDS})
            if not form.is_valid():
                messages.error(request, "لطفاً اطلاعات آدرس را کامل و درست وارد کنید.")
                return redirect("orders:checkout")
            address_data = {field: form.cleaned_data[field] for field in ADDRESS_FIELDS}
            save_address = request.POST.get("save_address") == "on"

        try:
            from apps.orders.models import Order, ShippingMethod

            shipping_method = None
            method_id = _posted_id(request, "shipping_method")
            if method_id:
                shipping_method = ShippingMethod.objects.filter(pk=method_id, is_active=True).first()
            order = services.place_order(
                user=request.user,
                cart=cart,
                address_data=address_data,
                coupon_code=request.session.get("coupon_code", ""),
                shipping_method=shipping_method,
                install_requested=request.POST.get("install_requested") == "on",
                install_date=request.POST.get("install_date", "").strip()[:30],
                pay_with_wallet=request.POST.get("pay_with_wallet") == "on",
            )
        except OrderError as exc:
            messages.error(request, str(exc))
            return redirect("orders:checkout")

        if save_address:
            from apps.accounts import services as account_services

            account_services.create_address(user=request.user, is_default=False, **address_data)
        request.session.pop("coupon_code", None)
        if order.status == Order.Status.PAID:
            return redirect("orders:success", order_number=order.order_number)
        return redirect("orders:pay", order_number=order.order_number)


class PayView(LoginRequiredMixin, View):
    """Start or resume the gateway payment; with the mock gateway this page *is* the bank."""

    def _get_order(self, request, order_number):
        order = services.get_user_order(request.user, order_number)
        if order is None:
            raise Http404("سفارش یافت نشد")
        return order

    def get(self, request, order_number):
        order = self._get_order(request, order_number)
        if order.status != Order.Status.PENDING_PAYMENT:
            return redirect("orders:detail", order_number=order.order_number)
        try:
            payment = start_payment(order=order)
        except PaymentError as exc:
            messages.error(request, f"اتصال به درگاه پرداخت انجام نشد: {exc}")
            return redirect("orders:detail", order_number=order.order_number)

        gateway = get_gateway()
        if gateway.name != "mock":
            return redirect(getattr(payment, "_redirect_url", "") or gateway.redirect_for_payment(payment))
        return render(request, "orders/pay.html", {"order": order, "payment": payment})

    def post(self, request, order_number):
        if get_gateway().name != "mock":
            raise Http404("درگاه شبیه‌ساز فعال نیست")
        order = self._get_order(request, order_number)
        payment = order.payments.filter(status=Payment.Status.CREATED).first()
        if payment is None:
            return redirect("orders:pay", order_number=order.order_number)
        try:
            complete_payment(payment=payment, outcome=request.POST.get("outcome", "success"))
        except PaymentError as exc:
            from apps.common import shoplog

            shoplog.payment_failed(order)
            messages.error(request, f"پرداخت ناموفق بود: {exc}")
            return redirect("orders:pay", order_number=order.order_number)
        return redirect("orders:success", order_number=order.order_number)


class OrderSuccessView(LoginRequiredMixin, TemplateView):
    template_name = "orders/order_success.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = services.get_user_order(self.request.user, kwargs["order_number"])
        if order is None:
            raise Http404("سفارش یافت نشد")
        context["order"] = order
        return context


class OrderListView(LoginRequiredMixin, ListView):
    template_name = "orders/order_list.html"
    context_object_name = "orders"
    paginate_by = 10

    def get_queryset(self):
        return Order.objects.filter(user=self.request.user)


class OrderDetailView(LoginRequiredMixin, DetailView):
    template_name = "orders/order_detail.html"
    context_object_name = "order"

    def get_object(self):
        order = services.get_user_order(self.request.user, self.kwargs["order_number"])
        if order is None:
            raise Http404("سفارش یافت نشد")
        return order

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        order = self.object
        context["return_requests"] = order.return_requests.prefetch_related("items__order_item")
        context["return_blocked"] = returns.return_block_reason(order)
        context["return_deadline"] = returns.return_deadline(order)
        return context


class InvoiceView(LoginRequiredMixin, View):
    """Printable invoice for the order's owner, or any order for staff."""

    def get(self, request, order_number):
        order = (
            Order.objects.select_related("user", "shipping_address", "shipping_method")
            .prefetch_related("items")
            .filter(order_number=order_number)
            .first()
        )
        # staff see any order only after the admin sign-in (including its SMS step)
        if order is None or not (order.user_id == request.user.pk or admin.site.has_permission(request)):
            raise Http404("سفارش یافت نشد")
        from apps.common.services import get_settings

        return render(request, "orders/invoice.html", {"order": order, "seller": get_settings()})


@method_decorator(ratelimit("return_request", limit=10, window=3600), name="dispatch")
class ReturnRequestCreateView(LoginRequiredMixin, View):
    template_name = "orders/return_form.html"

    def _order(self, request, order_number):
        order = services.get_user_order(request.user, order_number)
        if order is None:
            raise Http404("سفارش یافت نشد")
        return order

    def _render(self, request, order, form, quantities=None, error=""):
        available = returns.returnable_quantities(order)
        rows = [
            {
                "item": item,
                "available": available[item.pk],
                "options": range(available[item.pk] + 1),
                "selected": (quantities or {}).get(item.pk, 0),
            }
            for item in order.items.all()
        ]
        return render(request, self.template_name, {
            "order": order, "form": form, "rows": rows, "error": error,
            "deadline": returns.return_deadline(order),
        })

    def get(self, request, order_number):
        order = self._order(request, order_number)
        blocked = returns.return_block_reason(order)
        if blocked:
            messages.error(request, blocked)
            return redirect("orders:detail", order_number=order.order_number)
        return self._render(request, order, ReturnRequestForm())

    def post(self, request, order_number):
        order = self._order(request, order_number)
        form = ReturnRequestForm(request.POST, request.FILES)
        quantities = {}
        for item in order.items.all():
            try:
                quantities[item.pk] = max(0, int(request.POST.get(f"qty_{item.pk}", 0)))
            except (TypeError, ValueError):
                quantities[item.pk] = 0
        if not form.is_valid():
            return self._render(request, order, form, quantities)
        try:
            returns.create_return_request(
                order=order, quantities=quantities,
                reason=form.cleaned_data["reason"], resolution=form.cleaned_data["resolution"],
                description=form.cleaned_data["description"], image=form.cleaned_data.get("image"),
            )
        except returns.ReturnError as exc:
            return self._render(request, order, form, quantities, error=str(exc))
        messages.success(request, "درخواست مرجوعی ثبت شد؛ نتیجه بررسی از طریق پیامک یا ایمیل اطلاع داده می‌شود.")
        return redirect("orders:detail", order_number=order.order_number)


class ReturnRequestListView(LoginRequiredMixin, ListView):
    template_name = "orders/return_list.html"
    context_object_name = "return_requests"
    paginate_by = 10

    def get_queryset(self):
        return (
            ReturnRequest.objects.filter(order__user=self.request.user)
            .select_related("order")
            .prefetch_related("items__order_item")
        )


class OrderCancelView(LoginRequiredMixin, View):
    def post(self, request, order_number):
        order = services.get_user_order(request.user, order_number)
        if order is None:
            raise Http404("سفارش یافت نشد")
        try:
            services.cancel_pending_order(order=order)
            messages.success(request, "سفارش لغو شد و موجودی رزروشده آزاد گردید.")
        except OrderError as exc:
            messages.error(request, str(exc))
        return redirect("orders:detail", order_number=order.order_number)


TRACK_NOT_FOUND = "سفارشی با این شماره و موبایل پیدا نشد. شماره سفارش و موبایلی که هنگام خرید وارد کرده‌اید را بررسی کنید."


@method_decorator(
    ratelimit("order_track", limit=20, window=3600, key_fields=("order_number",), key_limit=8), name="dispatch"
)
class OrderTrackView(View):
    """Order status without signing in: the order number plus the mobile that ordered it."""

    template_name = "orders/track.html"

    def get(self, request):
        return render(request, self.template_name, {})

    def post(self, request):
        from django.db.models import Q

        from apps.accounts.otp import normalize_phone

        typed_number = (request.POST.get("order_number") or "").strip()
        typed_phone = (request.POST.get("phone") or "").strip()
        phone = normalize_phone(typed_phone)
        order = None
        if typed_number and phone:
            order = (
                Order.objects.filter(order_number__iexact=typed_number)
                .filter(Q(shipping_address__phone__in=[phone, typed_phone]) | Q(user__phone=phone))
                .select_related("shipping_address")
                .prefetch_related("items")
                .first()
            )
        return render(request, self.template_name, {
            "order": order,
            "order_number": typed_number,
            "phone": typed_phone,
            "error": "" if order else TRACK_NOT_FOUND,
        })
