from decimal import Decimal

import pytest
from django.core.exceptions import ValidationError
from django.core.management import call_command

from apps.catalog.models import Attribute, Category, Product, ProductAttributeValue
from apps.guides import services
from apps.guides.models import BuyingGuide, GuideAnswer, GuideQuestion

M = 1_000_000


@pytest.fixture
def fridges(db):
    category = Category.objects.create(name="یخچال و فریزر", slug="fridges")
    capacity = Attribute.objects.create(category=category, name="ظرفیت", unit="لیتر")
    compressor = Attribute.objects.create(category=category, name="کمپرسور")

    def fridge(slug, price, litres, comp, stock=3):
        product = Product.objects.create(category=category, name=f"یخچال {slug}", slug=slug, price=price, stock=stock)
        ProductAttributeValue.objects.create(product=product, attribute=capacity, value_text=f"{litres} لیتر")
        ProductAttributeValue.objects.create(product=product, attribute=compressor, value_text=comp)
        return product

    return {
        "category": category, "capacity": capacity, "compressor": compressor,
        "small": fridge("small", 12 * M, "۳۲۰", "معمولی"),
        "family": fridge("family", 25 * M, "550", "اینورتر"),
        "big": fridge("big", 45 * M, "700", "اینورتر"),
    }


@pytest.fixture
def guide(fridges):
    guide = BuyingGuide.objects.create(category=fridges["category"], title="کدام یخچال؟")
    people = GuideQuestion.objects.create(guide=guide, text="چند نفرید؟", sort_order=0)
    power = GuideQuestion.objects.create(guide=guide, text="مصرف برق مهم است؟", sort_order=1)
    budget = GuideQuestion.objects.create(guide=guide, text="بودجه؟", sort_order=2)
    options = {
        "few": GuideAnswer.objects.create(question=people, label="۱ تا ۲ نفر", attribute=fridges["capacity"], max_value=400),
        "four": GuideAnswer.objects.create(question=people, label="۳ تا ۴ نفر", attribute=fridges["capacity"],
                                           min_value=400, max_value=600, reason="مناسب خانواده ۴ نفره"),
        "inverter": GuideAnswer.objects.create(question=power, label="بله", attribute=fridges["compressor"], text_contains="اينورتر"),
        "any_power": GuideAnswer.objects.create(question=power, label="فرقی نمی‌کند"),
        "cheap": GuideAnswer.objects.create(question=budget, label="تا ۲۰ میلیون", price_max=20 * M, is_required=True),
        "mid": GuideAnswer.objects.create(question=budget, label="تا ۳۰ میلیون", price_max=30 * M, is_required=True),
    }
    guide.options = options
    guide.q = {"people": people, "power": power, "budget": budget}
    return guide


def ask(guide, **picked):
    params = {f"q{guide.q[question].pk}": str(guide.options[option].pk) for question, option in picked.items()}
    return services.recommend(guide, services.chosen_answers(guide, params))


def slugs(result):
    return [match.product.slug for match in result["matches"]]


def test_best_match_first_with_reasons(guide):
    result = ask(guide, people="four", power="inverter", budget="mid")
    assert slugs(result) == ["family", "small"]  # «big» is over the required budget
    best = result["matches"][0]
    assert best.percent == 100
    assert best.reasons == ["مناسب خانواده ۴ نفره", "کمپرسور: اینورتر", "قیمت 25,000,000 تومان"]
    assert result["matches"][1].misses == ["۳ تا ۴ نفر", "بله"]


def test_numbers_are_read_from_spec_text_in_any_digits(guide):
    assert services.spec_number(guide.options["few"].attribute.values.get(product__slug="small")) == Decimal("320")
    assert slugs(ask(guide, people="few"))[0] == "small"


def test_required_rule_with_no_match_falls_back_to_closest(guide, fridges):
    Product.objects.filter(slug="small").update(price=21 * M)
    result = ask(guide, people="few", budget="cheap")
    assert result["relaxed"]
    assert slugs(result)[0] == "small"


def test_no_answers_or_foreign_answers_are_ignored(guide, fridges):
    other = BuyingGuide.objects.create(category=Category.objects.create(name="x", slug="x"), title="x")
    foreign = GuideAnswer.objects.create(question=GuideQuestion.objects.create(guide=other, text="?"), label="?", price_max=1)
    params = {f"q{guide.q['people'].pk}": str(foreign.pk), f"q{guide.q['budget'].pk}": "abc"}
    assert services.chosen_answers(guide, params) == []


def test_in_stock_breaks_ties(guide, fridges):
    Product.objects.filter(slug="family").update(stock=0)
    result = ask(guide, power="any_power")
    assert slugs(result)[-1] == "family"


def test_guide_page(client, guide):
    page = client.get("/guide/fridges/")
    assert page.status_code == 200
    assert "چند نفرید؟" in page.content.decode()

    answered = client.get("/guide/fridges/", {f"q{guide.q['people'].pk}": guide.options["four"].pk})
    body = answered.content.decode()
    assert "بهترین انتخاب" in body and "یخچال family" in body
    assert client.get("/guide/").status_code == 200
    assert client.get("/guide/no-such/").status_code == 404


def test_category_page_links_to_its_guide(client, guide):
    assert "/guide/fridges/" in client.get("/c/fridges/").content.decode()


def test_header_link_appears_with_an_active_guide(client, fridges):
    assert "کمکم کن انتخاب کنم" not in client.get("/").content.decode()
    BuyingGuide.objects.create(category=fridges["category"], title="کدام یخچال؟")
    assert "کمکم کن انتخاب کنم" in client.get("/").content.decode()


def test_option_rules_are_validated(guide, fridges):
    washers = Category.objects.create(name="لباسشویی", slug="washers")
    drum = Attribute.objects.create(category=washers, name="ظرفیت")
    question = guide.q["people"]
    with pytest.raises(ValidationError):
        GuideAnswer(question=question, label="x", attribute=drum, min_value=5).full_clean()  # other category
    with pytest.raises(ValidationError):
        GuideAnswer(question=question, label="x", attribute=fridges["capacity"]).full_clean()  # no range
    with pytest.raises(ValidationError):
        GuideAnswer(question=question, label="x", min_value=5).full_clean()  # range without spec
    with pytest.raises(ValidationError):
        GuideAnswer(question=question, label="x", price_min=9, price_max=1).full_clean()


def test_seed_command_builds_guides_from_existing_specs(db):
    call_command("seed_appliances", verbosity=0)
    call_command("seed_buying_guides", stdout=None)
    call_command("seed_buying_guides")  # safe to re-run
    guide = BuyingGuide.objects.get(category__name="یخچال و فریزر")
    assert guide.questions.count() == 3
    assert BuyingGuide.objects.count() == 2
