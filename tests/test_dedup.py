import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dedup import Deduper, norm_company, SAME_SOURCE, OTHER_SOURCE  # noqa: E402
from models import Offer  # noqa: E402


def offer(title, company="Acme", source="nofluffjobs", sid="1"):
    return Offer(source=source, source_id=sid, url="", company=company, title=title)


def is_dup(first, second, **kw):
    dd = Deduper([])
    dd.add(first)
    return dd.check(second) is not None


def test_word_order_and_seniority_is_duplicate():
    assert is_dup(offer("Senior Android Developer"), offer("Android Developer (Senior)", sid="2"))


def test_different_tech_in_parens_is_not_duplicate():
    assert not is_dup(offer("Mobile Developer (Flutter)"), offer("Mobile Developer (Android)", sid="2"))


def test_subset_title_is_not_duplicate():
    assert not is_dup(offer("Developer"), offer("Android Developer", sid="2"))


def test_gender_marker_is_ignored():
    assert is_dup(offer("Android Developer (m/f)"), offer("Android Developer", sid="2"))


def test_company_normalization():
    assert norm_company("ACME Sp. z o.o.") == norm_company("Acme")


def test_reasons():
    dd = Deduper([("justjoinit:x", "Acme", "Android Developer")])
    assert dd.check(offer("Android Developer"))[0] == OTHER_SOURCE   # z arkusza
    dd = Deduper([])
    dd.add(offer("Android Developer"))
    assert dd.check(offer("Android Developer", sid="2"))[0] == SAME_SOURCE
    assert dd.check(offer("Android Developer", source="justjoinit", sid="3"))[0] == OTHER_SOURCE
