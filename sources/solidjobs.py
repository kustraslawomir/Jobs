"""SOLID.Jobs – oficjalne publiczne REST API (bez kluczy), dokumentacja: https://solid.jobs/api-ofert-pracy

GET https://solid.jobs/public-api/offers/IT?campaign=<własny-identyfikator>&pageSize=500&pageIndex=N
Zweryfikowane 2026-10-27. Limit 300 zapytań/min na IP, odpowiedzi cachowane godzinę; `campaign` to dowolny
identyfikator (małe litery, cyfry, myślniki, max 64 znaki) używany tylko do analityki po stronie portalu.
Dział IT ma ~1500 ofert (4 strony po 500, ~2.5 MB każda); API nie ma filtra po technologii, więc ofertę
zostawiamy dopiero gdy subCategory / tytuł / skille wskazują na Androida, Kotlina albo mobile.
Odpowiedź zawiera pełny opis (HTML), więc osobne details() nie jest potrzebne.
Widełki: salary (+ secondarySalary dla drugiej formy), kwoty miesięczne, employmentType to już kody B2B/UoP/UZ/UoD/Staż.
Link do oferty to adres zwrócony przez API (zawiera nasz identyfikator kampanii).
"""
import time
from models import Offer, Pay
from .htmlutil import clean_text

LIST_URL = "https://solid.jobs/public-api/offers/IT"
CAMPAIGN = "job-tracker-android"
PAGE_SIZE = 500
MAX_PAGES = 10
KEYWORDS = ("android", "kotlin", "mobile")
MONTH_HOURS = 168


def relevant(item: dict) -> bool:
    haystack = " ".join([item.get("title") or "", item.get("subCategory") or ""]
                        + [s.get("name", "") for s in item.get("skills") or [] if isinstance(s, dict)]).lower()
    return any(k in haystack for k in KEYWORDS)


def _pay(sal: dict | None) -> Pay | None:
    if not sal or (sal.get("from") is None and sal.get("to") is None):
        return None
    hourly = str(sal.get("period") or "").lower().startswith("hour")
    mult = MONTH_HOURS if hourly else 1
    lo, hi = sal.get("from"), sal.get("to")
    return Pay(sal.get("employmentType") or "", lo * mult if lo is not None else None,
               hi * mult if hi is not None else None, str(sal.get("currency") or "PLN").upper(),
               ((lo if lo is not None else hi), (hi if hi is not None else lo)) if hourly else None)


def to_offer(item: dict) -> Offer | None:
    key, url = item.get("jobOfferKey"), item.get("url")
    if not key or not url:
        return None
    pays = [p for p in (_pay(item.get("salary")), _pay(item.get("secondarySalary"))) if p]
    skills = [s.get("name", "") for s in item.get("skills") or [] if isinstance(s, dict)]
    return Offer(
        source="solidjobs", source_id=str(key), url=url,
        company=item.get("company") or "?", title=item.get("title") or "?",
        remote=bool(item.get("isRemote")), location=", ".join(item.get("locations") or []),
        pay=pays,
        description=" ".join([item.get("title") or ""] + skills + [clean_text(item.get("description") or "")]),
    )


def fetch(session) -> list[Offer]:
    out, seen = [], set()
    for page in range(MAX_PAGES):
        r = session.get(LIST_URL, params={"campaign": CAMPAIGN, "pageSize": PAGE_SIZE, "pageIndex": page},
                        headers={"Accept": "application/json"}, timeout=60)
        r.raise_for_status()
        data = r.json()
        for it in data.get("jobs") or []:
            o = to_offer(it) if relevant(it) else None
            if o and o.source_id not in seen:
                seen.add(o.source_id)
                out.append(o)
        if page + 1 >= (data.get("totalPages") or 1):
            break
        time.sleep(1.5)
    return out
