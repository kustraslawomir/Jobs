import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import passes_filters  # noqa: E402
from models import Offer, Pay  # noqa: E402

F = {"title_require_any": ["android"], "title_mobile_words": [], "title_dev_words": [], "title_exclude": [],
     "remote_only": True, "contract_allow": ["B2B", "UoP"], "min_salary_to_pln": 18000}


def o(**kw):
    return Offer(source="x", source_id="1", url="", company="Acme", title="Android Developer", remote=True, **kw)


def test_salary_text_lists_every_form():
    off = o(pay=[Pay("B2B", 23520, 29400, "PLN", (140, 175)), Pay("UoP", 18000, 22000)])
    assert off.salary_text() == "B2B 23 520–29 400 (140–175/h) | UoP 18 000–22 000"
    assert off.contract == ["B2B", "UoP"]
    assert off.salary_to == 29400


def test_equal_hourly_rate_is_single_number_and_foreign_currency_is_shown():
    assert o(pay=[Pay("B2B", 22680, 22680, "PLN", (135, 135))]).salary_text() == "B2B 22 680 (135/h)"
    assert o(pay=[Pay("B2B", 5000, 6000, "EUR")]).salary_text() == "B2B 5 000–6 000 EUR"


def test_no_pay_shows_contracts():
    assert o().salary_text() == "brak widełek"
    assert o(contract=["B2B"]).salary_text() == "brak widełek (B2B)"


def test_contract_filter():
    fx = {"PLN": 1}
    assert passes_filters(o(contract=["UZ"]), F, fx) == "forma współpracy"
    assert passes_filters(o(contract=["UZ", "B2B"]), F, fx) is None
    assert passes_filters(o(), F, fx) is None                      # brak podanej formy przechodzi
    assert passes_filters(o(contract=["b2b"]), F, fx) is None


def test_salary_range_spans_all_forms():
    off = o(pay=[Pay("B2B", 20000, 25000), Pay("UoP", 15000, 18000)])
    assert off.salary_range_pln({"PLN": 1}) == (15000, 25000)
