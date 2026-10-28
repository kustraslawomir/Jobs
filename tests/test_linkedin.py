import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.linkedin import parse_cards, parse_detail, details  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def test_cards_give_id_title_company_and_clean_link():
    offers = parse_cards(read("linkedin_search.html"))
    assert len(offers) == 3
    o = offers[0]
    assert (o.source, o.source_id, o.title, o.company) == ("linkedin", "4472070124", "Android Developer", "Comarch")
    assert o.url == "https://www.linkedin.com/jobs/view/4472070124" and o.remote is True and "Łódź" in o.location
    assert o.key == "linkedin:4472070124" and o.employment == []


def test_detail_has_description_and_criteria():
    text, criteria = parse_detail(read("linkedin_detail.html"))
    assert "Android Developer" in text and "<" not in text and len(text) > 200
    assert criteria["Employment type"] == "Full-time"


def test_details_adds_non_full_time_employment_type(monkeypatch):
    html = read("linkedin_detail.html").replace("Full-time", "Part-time")

    class R:
        text = html

        def raise_for_status(self):
            pass

    class S:
        def get(self, *a, **k):
            return R()
    monkeypatch.setattr("time.sleep", lambda s: None)
    o = parse_cards(read("linkedin_search.html"))[0]
    assert "Android Developer" in details(S(), o) and o.employment == ["Part-time"]
