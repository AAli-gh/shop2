"""The sales-rep panel (/rep/): only accounts the admin made active reps get in."""
import functools

from django.contrib import messages
from django.contrib.auth.views import redirect_to_login
from django.core.exceptions import PermissionDenied
from django.core.paginator import Paginator
from django.db.models import Count, Q, Sum
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.catalog.models import Category, Product
from apps.reps import services
from apps.reps.forms import PlaceOrderForm, RepCustomerForm
from apps.reps.services import RepOrderError


def rep_required(view):
    @functools.wraps(view)
    def wrapped(request, *args, **kwargs):
        if not request.user.is_authenticated:
            return redirect_to_login(request.get_full_path())
        rep = services.active_rep(request.user)
        if rep is None:
            raise PermissionDenied
        request.rep = rep
        return view(request, *args, **kwargs)

    return wrapped


def _render(request, template, context=None):
    return render(request, template, {"rep": request.rep, "basket_count": services.basket_lines(request.session)["count"],
                                      **(context or {})})


def _int(value, default=0):
    try:
        return int(value)
    except (TypeError, ValueError):
        return default


@rep_required
def dashboard(request):
    return _render(request, "reps/dashboard.html", {"stats": services.dashboard(request.rep)})


# ---------------------------------------------------------------- catalogue

@rep_required
def products(request):
    q = request.GET.get("q", "").strip()
    category = request.GET.get("category", "")
    in_stock = request.GET.get("stock") == "1"
    page = Paginator(services.catalogue(q=q, category=category, in_stock=in_stock), 24).get_page(request.GET.get("page"))
    return _render(request, "reps/products.html", {
        "page_obj": page, "q": q, "category": category, "in_stock": in_stock,
        "categories": Category.objects.filter(is_active=True, parent__isnull=True).order_by("name"),
    })


@rep_required
def product_sheet(request, pk):
    from apps.catalog.services import product_specs

    product = get_object_or_404(Product.objects.select_related("category", "brand"), pk=pk, is_active=True)
    return _render(request, "reps/product_sheet.html", {
        "product": product,
        "variants": product.variants.filter(is_active=True),
        "specs": product_specs(product),
        "public_url": request.build_absolute_uri(product.get_absolute_url()),
    })


@rep_required
@require_POST
def basket_add(request):
    product = get_object_or_404(Product, pk=_int(request.POST.get("product")), is_active=True)
    variant_id = _int(request.POST.get("variant")) or None
    if variant_id and not product.variants.filter(pk=variant_id, is_active=True).exists():
        variant_id = None
    if product.has_variants and not variant_id:
        messages.error(request, f"برای «{product.name}» رنگ یا مدل را انتخاب کنید.")
    else:
        quantity = max(1, _int(request.POST.get("quantity"), 1))
        services.add(request.session, product_id=product.pk, variant_id=variant_id, quantity=quantity)
        messages.success(request, f"{quantity} عدد «{product.name}» به سبد سفارش اضافه شد.")
    back = request.POST.get("next", "")
    if not url_has_allowed_host_and_scheme(back, allowed_hosts={request.get_host()}):
        back = "reps:products"
    return redirect(back)


# ---------------------------------------------------------------- basket and placing the order

@rep_required
def basket(request):
    rep = request.rep
    if request.method == "POST" and request.POST.get("action") == "update":
        for line in services.basket_lines(request.session)["lines"]:
            product_id, variant_id = (int(part) for part in line["key"].split(":"))
            services.set_quantity(request.session, product_id=product_id, variant_id=variant_id or None,
                                  quantity=_int(request.POST.get(f"qty_{line['key']}"), line["quantity"]))
        return redirect("reps:basket")

    form = PlaceOrderForm(request.POST or None, rep=rep, initial={"customer": request.GET.get("customer")})
    if request.method == "POST" and form.is_valid():
        try:
            order = services.place_from_basket(
                request.session, rep=rep, customer=form.cleaned_data["customer"],
                payment_terms=form.cleaned_data["payment_terms"], note=form.cleaned_data["note"],
            )
        except RepOrderError as exc:
            messages.error(request, str(exc))
        else:
            messages.success(request, f"سفارش {order.order_number} ثبت شد و منتظر تأیید شرکت است.")
            return redirect("reps:order_detail", order_number=order.order_number)
    return _render(request, "reps/basket.html", {"basket": services.basket_lines(request.session), "form": form})


# ---------------------------------------------------------------- orders

@rep_required
def orders(request):
    rep_orders = request.rep.orders.select_related("rep_customer").order_by("-created_at")
    customer = None
    if request.GET.get("customer"):
        customer = get_object_or_404(request.rep.customers, pk=_int(request.GET.get("customer")))
        rep_orders = rep_orders.filter(rep_customer=customer)
    status = request.GET.get("status", "")
    if status:
        rep_orders = rep_orders.filter(status=status)
    from apps.orders.models import Order

    return _render(request, "reps/orders.html", {
        "page_obj": Paginator(rep_orders, 20).get_page(request.GET.get("page")),
        "customer": customer, "status": status, "statuses": Order.Status.choices,
    })


def _rep_order(request, order_number):
    return get_object_or_404(
        request.rep.orders.select_related("rep_customer", "shipping_address").prefetch_related("items"),
        order_number=order_number,
    )


@rep_required
def order_detail(request, order_number):
    return _render(request, "reps/order_detail.html", {"order": _rep_order(request, order_number)})


@rep_required
@require_POST
def order_cancel(request, order_number):
    try:
        services.cancel_rep_order(rep=request.rep, order=_rep_order(request, order_number))
        messages.success(request, "سفارش لغو شد و موجودی آن آزاد شد.")
    except RepOrderError as exc:
        messages.error(request, str(exc))
    return redirect("reps:order_detail", order_number=order_number)


@rep_required
@require_POST
def order_reorder(request, order_number):
    order = _rep_order(request, order_number)
    added = services.reorder_into_basket(request.session, order)
    messages.success(request, f"{added} قلم از سفارش {order.order_number} به سبد اضافه شد؛ تعدادها را بررسی کنید.")
    return redirect(f"{reverse('reps:basket')}?customer={order.rep_customer_id or ''}")


# ---------------------------------------------------------------- customers (shops)

@rep_required
def customers(request):
    q = request.GET.get("q", "").strip()
    shops = request.rep.customers.annotate(
        order_count=Count("orders", filter=~Q(orders__status="cancelled")),
        order_total=Sum("orders__total", filter=~Q(orders__status="cancelled")),
    ).order_by("-is_active", "shop_name")
    if q:
        shops = shops.filter(Q(shop_name__icontains=q) | Q(owner_name__icontains=q) | Q(phone__icontains=q) | Q(city__icontains=q))
    return _render(request, "reps/customers.html", {"page_obj": Paginator(shops, 30).get_page(request.GET.get("page")), "q": q})


@rep_required
def customer_form(request, pk=None):
    instance = get_object_or_404(request.rep.customers, pk=pk) if pk else None
    form = RepCustomerForm(request.POST or None, instance=instance, initial=None if instance else {"is_active": True})
    if request.method == "POST" and form.is_valid():
        customer = form.save(commit=False)
        customer.rep = request.rep
        customer.save()
        messages.success(request, f"مشتری «{customer.shop_name}» ذخیره شد.")
        if request.GET.get("then") == "basket":
            return redirect(f"{reverse('reps:basket')}?customer={customer.pk}")
        return redirect("reps:customers")
    return _render(request, "reps/customer_form.html", {"form": form, "instance": instance})
