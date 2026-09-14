from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils.decorators import method_decorator
from django.views import View
from django.views.generic import DetailView, ListView, TemplateView

from apps.accounts.models import Address
from apps.cart import services as cart_services
from apps.orders import services
from apps.orders.models import Order
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
                code=coupon_code, subtotal=summary["subtotal"]
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


class PlaceOrderView(LoginRequiredMixin, View):
    def post(self, request):
        cart = cart_services.get_or_create_cart(request)
        address_id = request.POST.get("address_id")
        address_data = {}

        if address_id:
            address = get_object_or_404(Address, pk=address_id, user=request.user)
            address_data = {
                "full_name": address.full_name,
                "phone": address.phone,
                "province": address.province,
                "city": address.city,
                "postal_code": address.postal_code,
                "address_line": address.address_line,
            }
        else:
            address_data = {
                "full_name": request.POST.get("full_name", "").strip(),
                "phone": request.POST.get("phone", "").strip(),
                "province": request.POST.get("province", "").strip(),
                "city": request.POST.get("city", "").strip(),
                "postal_code": request.POST.get("postal_code", "").strip(),
                "address_line": request.POST.get("address_line", "").strip(),
            }
            if not all(address_data.values()):
                messages.error(request, "لطفاً اطلاعات آدرس را کامل وارد کنید.")
                return redirect("orders:checkout")

            if request.POST.get("save_address") == "on":
                from apps.accounts import services as account_services

                account_services.create_address(user=request.user, is_default=False, **address_data)

        try:
            from apps.orders.models import Order, ShippingMethod

            shipping_method = None
            method_id = request.POST.get("shipping_method")
            if method_id:
                shipping_method = ShippingMethod.objects.filter(pk=method_id, is_active=True).first()
            order = services.place_order(
                user=request.user,
                cart=cart,
                address_data=address_data,
                coupon_code=request.session.get("coupon_code", ""),
                shipping_method=shipping_method,
                install_requested=request.POST.get("install_requested") == "on",
                install_date=request.POST.get("install_date", "").strip(),
                pay_with_wallet=request.POST.get("pay_with_wallet") == "on",
            )
        except OrderError as exc:
            messages.error(request, str(exc))
            return redirect("orders:checkout")

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
