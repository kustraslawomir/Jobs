import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.bulldogjob import parse_listing, to_offer  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def offers():
    items, total = parse_listing(open(os.path.join(FIX, "bulldogjob_listing.html"), encoding="utf-8").read())
    assert total == len(items) == 4
    return {o.source_id.split("-")[0]: o for o in map(to_offer, items)}


def test_b2b_remote_offer_with_salary():
    o = offers()["259686"]
    assert o.company == "TeamQuest" and o.remote is True and o.contract == ["B2B"]
    assert o.salary_text() == "B2B 26 000–32 000"
    assert o.url == "https://bulldogjob.pl/companies/jobs/" + o.source_id


def test_employment_offer_without_salary():
    o = offers()["259551"]
    assert o.contract == ["UoP"] and o.pay == [] and o.salary_text() == "brak widełek (UoP)"
    assert "Android" in o.title


def test_employment_offer_with_salary_is_labeled_uop():
    o = offers()["258848"]
    assert o.remote is False and o.salary_text() == "UoP 54 000–64 000"


def test_listing_without_next_data_is_an_error():
    with pytest.raises(ValueError):
        parse_listing("<html>Just a moment...</html>")
