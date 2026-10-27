"""JustJoinIT – endpoint zweryfikowany 2026-10-27 w przeglądarce.

GET https://justjoin.it/api/candidate-api/offers
  ?keywords=android&keywordType=any&sortBy=publishedAt&orderBy=descending&perPage=10&from=0
Odpowiedź: {"data": [...], "meta": {"totalItems", "next": {"cursor"}}}
Filtra remote po stronie API nie ma (parametr ignorowany) – remote filtruje main.py.
Ta sama oferta w kilku miastach to JEDEN rekord z listą "locations", więc tu nie ma duplikatów per miasto.
"""
import html
import json
import re
import time
from models import Offer

LIST_URL = "https://justjoin.it/api/candidate-api/offers"
PARAMS = {"keywords": "android", "keywordType": "any", "sortBy": "publishedAt",
          "orderBy": "descending", "perPage": 10}
HEADERS = {"Accept": "application/json", "Referer": "https://justjoin.it/job-offers?keyword=android"}
OFFER_URL = "https://justjoin.it/job-offer/{slug}"
MAX_PAGES = 40  # API ignoruje perPage i daje max 10 na stronę: 40 x 10 = 400 najnowszych


def _salary(item):
    from . import pick
    types = pick(item, "employmentTypes", default=[]) or []

    def score(et):
        # preferuj: oryginalna waluta PLN > dowolna PLN > B2B > reszta
        cur = str(et.get("currency", "")).upper()
        return ((cur == "PLN") * 4 + (et.get("currencySource") == "original") * 2
                + (str(et.get("type", "")).lower() == "b2b"))

    cands = [et for et in types if isinstance(et, dict) and et.get("to") is not None]
    if not cands:
        return None, None, "", "month", ""
    best = max(cands, key=score)
    # from/to to zawsze kwoty miesięczne; stawkę godzinową (fromPerUnit/toPerUnit) dopisujemy tylko dla unit == Hour
    unit = str(best.get("unit", "Month")).lower()
    typ = str(best.get("type", "")).lower()
    contract = {"b2b": "B2B", "permanent": "UoP", "mandate_contract": "UZ"}.get(typ, typ)
    if "hour" in unit and best.get("fromPerUnit") is not None and best.get("toPerUnit") is not None:
        lo, hi = round(best["fromPerUnit"]), round(best["toPerUnit"])
        contract = f"{contract} ({lo}/h)" if lo == hi else f"{contract} ({lo}–{hi}/h)"
    return best.get("from"), best.get("to"), str(best.get("currency", "")).upper(), "month", contract


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
            sf, st, cur, per, con = _salary(it)
            wt = str(pick(it, "workplaceType", default="")).lower()
            cities = [l.get("city", "") for l in (pick(it, "locations", default=[]) or []) if isinstance(l, dict)]
            skills = _skills(it, "requiredSkills") + _skills(it, "niceToHaveSkills")
            out.append(Offer(
                source="justjoinit", source_id=str(oid), url=OFFER_URL.format(slug=slug),
                company=pick(it, "companyName", default="?"), title=pick(it, "title", default="?"),
                remote=(wt == "remote") if wt else None,
                location=", ".join(dict.fromkeys(c for c in cities if c)) or pick(it, "city", default=""),
                salary_from=sf, salary_to=st, currency=cur, salary_period=per, contract=con,
                description=" ".join([pick(it, "title", default="")] + skills),
            ))
        nxt = pick(data, "meta.next.cursor")
        if not items or nxt is None or nxt == cursor:
            break
        cursor = nxt
        time.sleep(1.5)
    return out


_LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def _clean(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()


def _job_posting_description(page: str) -> str:
    """Opis z JSON-LD (schema.org JobPosting): stabilniejszy niż klasy CSS czy wewnętrzny stan Next.js."""
    for m in _LD_JSON.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        for node in data if isinstance(data, list) else [data]:
            if isinstance(node, dict) and node.get("@type") == "JobPosting" and node.get("description"):
                return _clean(str(node["description"]))
    return ""


def details(session, offer: Offer) -> str:
    """Pełny opis do ATS: tytuł + skille z listy + tekst oferty. Wołane tylko dla ofert po filtrach i dedupie."""
    r = session.get(offer.url, headers={"Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    text = _job_posting_description(r.text) or _clean(_DROP.sub(" ", r.text))   # fallback: cały tekst strony
    time.sleep(1.5)
    return f"{offer.description} {text}"
