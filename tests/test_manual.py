import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import manual  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")


class Resp:
    def __init__(self, text, status=200):
        self.text, self.status_code = text, status


class Session:
    def __init__(self, resp=None, boom=False):
        self.resp, self.boom, self.urls = resp, boom, []

    def get(self, url, **kw):
        self.urls.append(url)
        if self.boom:
            raise OSError("sieć")
        return self.resp


def test_canonical_strips_tracking_and_normalizes_linkedin():
    assert manual.canonical("https://pl.linkedin.com/jobs/view/android-developer-at-comarch-4472070124?position=1&trk=x") == \
        "https://www.linkedin.com/jobs/view/4472070124"
    assert manual.canonical("https://www.linkedin.com/jobs/collections/recommended/?currentJobId=4472070124") == \
        "https://www.linkedin.com/jobs/view/4472070124"
    assert manual.canonical("https://Example.com/job/1/?utm_source=x#top") == "https://example.com/job/1"


def test_pasted_text_is_the_description_and_page_gives_title_and_company():
    page = ('<html><script type="application/ld+json">{"@type":"JobPosting","title":"Android Dev",'
            '"hiringOrganization":{"name":"Acme"},"description":"opis ze strony"}</script></html>')
    o, notes = manual.build_offer(Session(Resp(page)), "https://example.com/job/1", "mój wklejony opis, 1/2 etatu")
    assert (o.source, o.company, o.title, o.description) == ("ręcznie", "Acme", "Android Dev", "mój wklejony opis, 1/2 etatu")
    assert o.key.startswith("ręcznie:") and notes == []


def test_no_text_uses_fetched_description():
    page = ('<script type="application/ld+json">{"@type":"JobPosting","title":"T","hiringOrganization":{"name":"C"},'
            '"description":"opis ze strony"}</script>')
    o, notes = manual.build_offer(Session(Resp(page)), "https://example.com/job/1", None)
    assert o.description == "opis ze strony" and notes == []


def test_failed_fetch_without_text_keeps_the_link_and_asks_for_manual_completion():
    o, notes = manual.build_offer(Session(boom=True), "https://example.com/job/1", "")
    assert o.url == "https://example.com/job/1" and o.description == "" and o.company == "?"
    assert "Uzupełnij opis ręcznie" in notes and "Uzupełnij firmę i stanowisko" in notes


def test_cloudflare_challenge_counts_as_failed_fetch():
    o, notes = manual.build_offer(Session(Resp("<title>Just a moment...</title>", 403)), "https://example.com/x", None)
    assert "Uzupełnij opis ręcznie" in notes


def test_linkedin_link_uses_guest_detail_endpoint():
    page = ('<h2 class="top-card-layout__title font-sans">Android Developer</h2><a class="topcard__org-name-link x">Comarch</a>'
            + open(os.path.join(FIX, "linkedin_detail.html"), encoding="utf-8").read().replace("Full-time", "Part-time"))
    s = Session(Resp(page))
    o, notes = manual.build_offer(s, "https://pl.linkedin.com/jobs/view/android-developer-at-comarch-4472070124?trk=x", None)
    assert s.urls == ["https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/4472070124"]
    assert (o.company, o.title, o.url, o.employment) == ("Comarch", "Android Developer",
                                                         "https://www.linkedin.com/jobs/view/4472070124", ["Part-time"])
    assert len(o.description) > 200 and notes == []
