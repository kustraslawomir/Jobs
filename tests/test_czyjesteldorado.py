import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.czyjesteldorado import parse_search, to_offer, _pay  # noqa: E402
from sources.htmlutil import job_posting_description  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def load(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def offers():
    return {o.source_id: o for o in (to_offer(i) for i in parse_search(load("czyjesteldorado_search.html")))}


def test_parses_all_jobs_from_embedded_payload():
    assert set(offers()) == {"465858", "456288", "262739", "335748"}


def test_hourly_rate_becomes_monthly_with_hourly_in_brackets():
    o = offers()["465858"]
    assert o.url == "https://czyjesteldorado.pl/praca/465858-" + o.url.rsplit("465858-", 1)[1]
    assert o.company == "Ideamotive" and o.remote is True and o.contract == ["B2B"]
    assert (o.pay[0].lo, o.pay[0].hi, o.pay[0].hourly) == (130 * 168, 180 * 168, (130, 180))
    assert o.salary_text() == "B2B 21 840–30 240 (130–180/h)"


def test_daily_rate_is_converted_to_month_without_hourly_part():
    o = offers()["335748"]
    assert o.salary_text() == "B2B 29 400–34 650" and o.pay[0].hourly is None


def test_contract_without_amounts_is_listed_but_has_no_pay():
    o = offers()["456288"]
    assert o.contract == ["UoP", "B2B"] and o.pay == [] and o.salary_text() == "brak widełek (UoP, B2B)"
    assert o.remote is False                                   # hybrid


def test_unknown_contract_type_means_no_information():
    o = offers()["262739"]
    assert o.contract == [] and o.pay == []


def test_multiple_forms_each_get_their_own_pay():
    contracts, pays = _pay({"contractTypes": ["employment_contract", "b2b"], "salary": [
        {"contractType": "employment_contract", "period": "month", "currency": "PLN", "min": 18000, "max": 22000},
        {"contractType": "b2b", "period": "hour", "currency": "PLN", "min": 140, "max": 175}]})
    assert contracts == ["UoP", "B2B"]
    assert [(p.contract, p.lo, p.hi, p.hourly) for p in pays] == [
        ("UoP", 18000, 22000, None), ("B2B", 23520, 29400, (140, 175))]


def test_description_from_offer_page_json_ld():
    text = job_posting_description(load("offer_page_jsonld.html"))
    assert "Kotlin Multiplatform" in text and "<" not in text and "reszta strony" not in text
