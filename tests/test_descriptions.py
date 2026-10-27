import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from models import Offer  # noqa: E402
from sources import justjoinit, nofluffjobs  # noqa: E402
from sources.htmlutil import job_posting_description  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


def read(name):
    return open(os.path.join(FIX, name), encoding="utf-8").read()


def test_jjit_json_ld_glues_paragraphs_but_dom_block_does_not():
    page = read("jjit_offer_page.html")
    glued = job_posting_description(page)
    assert "Kotlin Multiplatform solutionsIntegrate" in glued             # to psuło porównania treści
    text = justjoinit.page_description(page)
    assert "Kotlin Multiplatform solutions Integrate" in text
    assert "Nagłówek strony" not in text and "Stopka" not in text and "<" not in text


def test_jjit_falls_back_to_json_ld_when_dom_block_does_not_match():
    page = read("jjit_offer_page.html").replace("Job description</h3>", "Job description</h3 >").replace(
        "<h3", "<h4")
    assert justjoinit.page_description(page) == job_posting_description(page)


class FakeSession:
    def __init__(self, payload):
        self.payload = payload

    def get(self, url, **kw):
        outer = self

        class R:
            def raise_for_status(self):
                pass

            def json(self):
                return outer.payload
        return R()


def test_nfj_details_use_both_description_fields_and_strip_html(monkeypatch):
    monkeypatch.setattr(nofluffjobs.time, "sleep", lambda s: None)
    payload = json.loads(read("nfj_posting_detail.json"))
    o = Offer(source="nofluffjobs", source_id="x", url="", company="Upvanta", title="Senior Android Developer",
              description="Senior Android Developer Android")
    text = nofluffjobs.details(FakeSession(payload), o)
    assert "płatności zbliżeniowych" in text           # details.description (opis projektu)
    assert "minimum 5" in text                          # requirements.description
    assert "<" not in text and "div" not in text.split()
