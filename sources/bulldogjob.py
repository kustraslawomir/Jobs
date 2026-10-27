"""bulldogjob.pl – oferty z listy wyszukiwania po technologii.

Metoda: dane osadzone w HTML (`<script id="__NEXT_DATA__">`, props.pageProps.jobs) na stronie
  GET https://bulldogjob.pl/companies/jobs/s/skills,Android      (oraz skills,Kotlin)
Zweryfikowane 2026-10-27. robots.txt nie zabrania /companies/jobs. Pominięto /withSalary,true i /page*
(zabronione); lista Android to ~15 ofert, więc jedna strona (perPage 50) wystarcza. Gdy totalCount
przekroczy liczbę ofert na stronie, fetch() zgłasza błąd zamiast po cichu gubić oferty.
Pola: id "255098-android-...", position, company.name, remote (bool), contractB2b / contractEmployment,
denominatedSalaryLong {money "20 000 - 25 000", currency, hidden} – kwota MIESIĘCZNA (JSON-LD oferty ma
unitText "month"); wartości poniżej 1500 traktujemy jako stawkę godzinową.
Lista podaje jedną kwotę bez przypisania do formy: etykietę formy dajemy tylko, gdy oferta ma dokładnie jedną.
Pełny opis: JSON-LD JobPosting ze strony oferty (details()).
"""
import json
import re
import time
from models import Offer, Pay
from .htmlutil import clean_text, job_posting_description, page_text

LIST_URL = "https://bulldogjob.pl/companies/jobs/s/skills,{skill}"
OFFER_URL = "https://bulldogjob.pl/companies/jobs/{id}"
SKILLS = ["Android", "Kotlin"]
MONTH_HOURS = 168
HOURLY_BELOW = 1500
_NEXT_DATA = re.compile(r'<script id="__NEXT_DATA__" type="application/json">(.*?)</script>', re.S)
_AMOUNT = re.compile(r"\d{1,3}(?:[  ]\d{3})+|\d+")


def parse_listing(page: str) -> tuple[list[dict], int]:
    m = _NEXT_DATA.search(page)
    if not m:
        raise ValueError("brak __NEXT_DATA__ (zmienił się układ strony?)")
    pp = json.loads(m.group(1))["props"]["pageProps"]
    return pp.get("jobs") or [], pp.get("totalCount") or 0


def _pay(item: dict, contracts: list[str]) -> list[Pay]:
    sal = item.get("denominatedSalaryLong") or {}
    if sal.get("hidden") or not sal.get("money"):
        return []
    nums = [float(re.sub(r"\D", "", a)) for a in _AMOUNT.findall(sal["money"])]
    if not nums:
        return []
    lo, hi = nums[0], nums[-1]
    hourly = (lo, hi) if hi < HOURLY_BELOW else None
    mult = MONTH_HOURS if hourly else 1
    return [Pay(contracts[0] if len(contracts) == 1 else "", lo * mult, hi * mult,
                str(sal.get("currency") or "PLN").upper(), hourly)]


def to_offer(item: dict) -> Offer | None:
    oid = item.get("id")
    if not oid:
        return None
    contracts = [name for flag, name in (("contractB2b", "B2B"), ("contractEmployment", "UoP")) if item.get(flag)]
    remote = item.get("remote")
    return Offer(
        source="bulldogjob", source_id=str(oid), url=OFFER_URL.format(id=oid),
        company=(item.get("company") or {}).get("name") or "?", title=item.get("position") or "?",
        remote=remote if isinstance(remote, bool) else None, location=item.get("city") or "",
        contract=contracts, pay=_pay(item, contracts),
        description=" ".join([item.get("position") or ""] + list(item.get("technologyTags") or [])),
    )


def fetch(session) -> list[Offer]:
    out, seen = [], set()
    for skill in SKILLS:
        r = session.get(LIST_URL.format(skill=skill), timeout=30)
        r.raise_for_status()
        items, total = parse_listing(r.text)
        if total > len(items):
            raise ValueError(f"skills,{skill}: {total} ofert, ale strona zawiera {len(items)} (potrzebna paginacja)")
        for it in items:
            o = to_offer(it)
            if o and o.source_id not in seen:
                seen.add(o.source_id)
                out.append(o)
        time.sleep(1.5)
    return out


def details(session, offer: Offer) -> str:
    """Pełny opis do ATS: tytuł + technologie z listy + tekst z JSON-LD strony oferty."""
    r = session.get(offer.url, headers={"Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    text = job_posting_description(r.text) or page_text(r.text)
    time.sleep(1.5)
    return f"{offer.description} {text}"
