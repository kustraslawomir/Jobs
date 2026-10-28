"""JustJoinIT – endpoint zweryfikowany 2026-10-27 w przeglądarce.

GET https://justjoin.it/api/candidate-api/offers
  ?keywords=android&keywordType=any&sortBy=publishedAt&orderBy=descending&perPage=10&from=0
Odpowiedź: {"data": [...], "meta": {"totalItems", "next": {"cursor"}}}
Filtra remote po stronie API nie ma (parametr ignorowany) – remote filtruje main.py.
Ta sama oferta w kilku miastach to JEDEN rekord z listą "locations", więc tu nie ma duplikatów per miasto.
"""
import re
import time
from models import Offer, Pay
from contracts import normalize
from .htmlutil import clean_text, job_posting_description as _job_posting_description, page_text

LIST_URL = "https://justjoin.it/api/candidate-api/offers"
PARAMS = {"keywords": "android", "keywordType": "any", "sortBy": "publishedAt",
          "orderBy": "descending", "perPage": 10}
HEADERS = {"Accept": "application/json", "Referer": "https://justjoin.it/job-offers?keyword=android"}
OFFER_URL = "https://justjoin.it/job-offer/{slug}"
MAX_PAGES = 40  # API ignoruje perPage i daje max 10 na stronę: 40 x 10 = 400 najnowszych


def _pay(item):
    """Zwraca (formy współpracy, widełki per forma). from/to w API to zawsze kwoty miesięczne;
    stawkę godzinową (fromPerUnit/toPerUnit) dopisujemy tylko dla unit == Hour."""
    from . import pick
    by_type: dict[str, list] = {}
    for et in pick(item, "employmentTypes", default=[]) or []:
        if isinstance(et, dict):
            by_type.setdefault(str(et.get("type", "")).lower(), []).append(et)

    def score(et):
        # preferuj: oryginalna waluta PLN > dowolna PLN > reszta
        return (str(et.get("currency", "")).upper() == "PLN") * 2 + (et.get("currencySource") == "original")

    contracts, pays = [], []
    for typ, ets in by_type.items():
        name = normalize(typ)
        if name and name not in contracts:
            contracts.append(name)
        cands = [e for e in ets if e.get("to") is not None]
        if not cands:
            continue
        best = max(cands, key=score)
        hourly = None
        if "hour" in str(best.get("unit", "")).lower() and None not in (best.get("fromPerUnit"), best.get("toPerUnit")):
            hourly = (best["fromPerUnit"], best["toPerUnit"])
        pays.append(Pay(name, best.get("from"), best.get("to"), str(best.get("currency", "")).upper() or "PLN", hourly))
    return contracts, pays


def _skills(item, key):
    from . import pick
    out = []
    for s in pick(item, key, default=[]) or []:
        out.append(s if isinstance(s, str) else (s.get("name") or ""))
    return [s for s in out if s]


def fetch(session) -> list[Offer]:
    from . import pick
    out, cursor = [], 0
    for _ in range(MAX_PAGES):
        r = session.get(LIST_URL, params={**PARAMS, "from": cursor}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = pick(data, "data", default=[]) or []
        for it in items:
            oid = pick(it, "guid", "slug")
            slug = pick(it, "slug")
            if not oid or not slug:
                continue
            contracts, pays = _pay(it)
            wt = str(pick(it, "workplaceType", default="")).lower()
            cities = [l.get("city", "") for l in (pick(it, "locations", default=[]) or []) if isinstance(l, dict)]
            skills = _skills(it, "requiredSkills") + _skills(it, "niceToHaveSkills")
            out.append(Offer(
                source="justjoinit", source_id=str(oid), url=OFFER_URL.format(slug=slug),
                company=pick(it, "companyName", default="?"), title=pick(it, "title", default="?"),
                remote=(wt == "remote") if wt else None,
                location=", ".join(dict.fromkeys(c for c in cities if c)) or pick(it, "city", default=""),
                contract=contracts, pay=pays, seniority=pick(it, "experienceLevel", default=""),
                employment=pick(it, "workingTime", default=""),
                description=" ".join([pick(it, "title", default="")] + skills),
            ))
        nxt = pick(data, "meta.next.cursor")
        if not items or nxt is None or nxt == cursor:
            break
        cursor = nxt
        time.sleep(1.5)
    return out


_DESC_START = re.compile(r'<h3[^>]*>[^<]{2,40}</h3><div class="[^"]*">(?=<(?:p|ul|ol|h[1-6])\b)')
_DIV = re.compile(r"</?div\b[^>]*>")


def _squash(text: str) -> str:
    return re.sub(r"\W+", "", text).lower()


def _dom_description(page: str) -> str:
    """Blok opisu z DOM strony (HTML Quill: <p>, <li>...). JSON-LD ma ten sam tekst, ale ze sklejonymi akapitami
    i punktami ("StackAutomotive", "QNXProgramming"), co psuje porównywanie treści i dopasowanie skilli w ATS."""
    m = _DESC_START.search(page)
    if not m:
        return ""
    depth = 1
    for tag in _DIV.finditer(page, m.end()):
        depth += -1 if tag.group(0).startswith("</") else 1
        if depth == 0:
            return clean_text(page[m.end():tag.start()])
    return ""


def page_description(page: str) -> str:
    """Opis oferty: tekst z DOM, o ile zgadza się z JSON-LD (inaczej układ strony się zmienił i bierzemy JSON-LD)."""
    ld, dom = _job_posting_description(page), _dom_description(page)
    x, y = _squash(ld), _squash(dom)
    if dom and ld and min(len(x), len(y)) >= 0.9 * max(len(x), len(y)) and (x in y or y in x):
        return dom
    return ld


def details(session, offer: Offer) -> str:
    """Pełny opis do ATS: tytuł + skille z listy + tekst oferty. Wołane tylko dla ofert po filtrach."""
    r = session.get(offer.url, headers={"Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    text = page_description(r.text) or page_text(r.text)      # fallback: cały tekst strony
    time.sleep(1.5)
    return f"{offer.description} {text}"
