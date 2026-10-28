"""LinkedIn Jobs – publiczny endpoint "guest" (bez logowania i bez konta), zweryfikowany 2026-10-28.

GET https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search
  ?keywords=android&location=Poland&f_WT=2&f_TPR=r2592000&sortBy=DD&start=0
f_WT=2 = zdalnie, f_TPR=r2592000 = ostatnie 30 dni, sortBy=DD = od najnowszych. Filtr f_JT (typ zatrudnienia) ten endpoint
ignoruje (te same wyniki dla P, C i F), więc część etatu / kontrakt rozpoznajemy dopiero ze szczegółów (Employment type) i z tekstu.
Odpowiedź to fragment HTML z 10 kartami (<li>) na stronę. Szczegóły oferty:
GET https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}  (opis + Employment type).
LinkedIn nie podaje widełek ani formy współpracy. Łamie to regulamin serwisu i IP serwerowni bywa blokowane (HTTP 429),
więc źródło działa na runnerze lokalnym; błąd 429 = źródło zgłasza błąd, reszta źródeł działa dalej.
Postów (wyszukiwanie treści) nie da się czytać bez logowania, więc ich tu nie ma.
"""
import re
import time
from models import Offer
from .htmlutil import clean_text

SEARCH_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"
DETAIL_URL = "https://www.linkedin.com/jobs-guest/jobs/api/jobPosting/{id}"
OFFER_URL = "https://www.linkedin.com/jobs/view/{id}"
KEYWORDS = ["android", "kotlin"]
MAX_PAGES = 5                    # 10 ofert na stronę
HEADERS = {"Accept-Language": "pl-PL,pl;q=0.9,en;q=0.8", "Accept": "text/html"}
PARAMS = {"location": "Poland", "f_WT": "2", "f_TPR": "r2592000", "sortBy": "DD"}

_CARD = re.compile(r"<li>(.*?)</li>", re.S)
_ID = re.compile(r"jobPosting:(\d+)")
_TITLE = re.compile(r'base-search-card__title">\s*(.*?)\s*</h3>', re.S)
_COMPANY = re.compile(r'base-search-card__subtitle">(.*?)</h4>', re.S)
_PLACE = re.compile(r'job-search-card__location">\s*(.*?)\s*</span>', re.S)
_CRITERIA = re.compile(r'description__job-criteria-subheader">\s*(.*?)\s*</h3>\s*<span[^>]*>\s*(.*?)\s*</span>', re.S)
_DESC = re.compile(r'show-more-less-html__markup[^>]*>(.*?)</div>', re.S)


def parse_cards(page: str) -> list[Offer]:
    out = []
    for card in _CARD.findall(page):
        m = _ID.search(card)
        title, company = _TITLE.search(card), _COMPANY.search(card)
        if not (m and title and company):
            continue
        place = _PLACE.search(card)
        out.append(Offer(
            source="linkedin", source_id=m.group(1), url=OFFER_URL.format(id=m.group(1)),
            company=clean_text(company.group(1)) or "?", title=clean_text(title.group(1)) or "?",
            remote=True, location=clean_text(place.group(1)) if place else "",
            description=clean_text(title.group(1)),
        ))
    return out


def parse_detail(page: str) -> tuple[str, dict[str, str]]:
    """(tekst opisu, kryteria: "Employment type" -> "Part-time" itd.)."""
    m = _DESC.search(page)
    return (clean_text(m.group(1)) if m else ""), {clean_text(k): clean_text(v) for k, v in _CRITERIA.findall(page)}


def fetch(session) -> list[Offer]:
    out, seen = [], set()
    for kw in KEYWORDS:
        for page in range(MAX_PAGES):
            r = session.get(SEARCH_URL, params={**PARAMS, "keywords": kw, "start": page * 10}, headers=HEADERS, timeout=30)
            r.raise_for_status()
            cards = parse_cards(r.text)
            for o in cards:
                if o.source_id not in seen:
                    seen.add(o.source_id)
                    out.append(o)
            time.sleep(2)
            if len(cards) < 10:
                break
    return out


def details(session, offer: Offer) -> str:
    """Opis do ATS i Poziomu; dopisuje do oferty typ zatrudnienia z LinkedIn (Part-time, Contract...)."""
    r = session.get(DETAIL_URL.format(id=offer.source_id), headers=HEADERS, timeout=30)
    r.raise_for_status()
    text, criteria = parse_detail(r.text)
    etype = criteria.get("Employment type") or criteria.get("Rodzaj zatrudnienia") or ""
    if etype and etype.lower() not in ("full-time", "pełny etat") and etype not in offer.employment:
        offer.employment.append(etype)
    time.sleep(2)
    return f"{offer.description} {text}"
