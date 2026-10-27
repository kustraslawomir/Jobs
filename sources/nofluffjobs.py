"""NoFluffJobs. Kategoria "android".

DO WERYFIKACJI w DevTools: SEARCH_URL, body zapytania i nazwy pól w odpowiedzi.
"""
import time
from models import Offer

SEARCH_URL = "https://nofluffjobs.com/api/search/posting"
PARAMS = {"salaryCurrency": "PLN", "salaryPeriod": "month", "region": "pl"}
BODY = {"criteriaSearch": {"category": ["android"]}, "page": 1}
DETAIL_URL = "https://nofluffjobs.com/api/posting/{id}"
OFFER_URL = "https://nofluffjobs.com/pl/job/{slug}"
FETCH_DETAILS = True   # dociąga wymagania (must/nice) -> lepszy ATS, 1 request na NOWĄ ofertę


def fetch(session) -> list[Offer]:
    from . import pick
    r = session.post(SEARCH_URL, params=PARAMS, json=BODY, timeout=30)
    r.raise_for_status()
    out = []
    for it in pick(r.json(), "postings", default=[]) or []:
        pid = pick(it, "id")
        if not pid:
            continue
        typ = str(pick(it, "salary.type", default="")).lower()
        out.append(Offer(
            source="nofluffjobs", source_id=str(pid),
            url=OFFER_URL.format(slug=pick(it, "url", default=pid)),
            company=pick(it, "name", "company.name", default="?"), title=pick(it, "title", default="?"),
            remote=pick(it, "location.fullyRemote", default=None),
            location=pick(it, "location.places.0.city", default=""),
            salary_from=pick(it, "salary.from"), salary_to=pick(it, "salary.to"),
            currency=str(pick(it, "salary.currency", default="")).upper(),
            contract={"b2b": "B2B", "permanent": "UoP"}.get(typ, typ),
            description=" ".join([pick(it, "title", default=""), str(pick(it, "technology", default=""))]),
        ))
    return out


def details(session, offer: Offer) -> str:
    """Pełne wymagania do ATS. Wołane tylko dla ofert, które przeszły dedup i filtry."""
    from . import pick
    r = session.get(DETAIL_URL.format(id=offer.source_id), timeout=30)
    r.raise_for_status()
    d = r.json()
    parts = [offer.title]
    for path in ("requirements.musts", "requirements.nices"):
        for x in pick(d, path, default=[]) or []:
            parts.append(x if isinstance(x, str) else pick(x, "value", "name", default=""))
    parts.append(str(pick(d, "requirements.description", "details.description", default="")))
    time.sleep(1)
    return " ".join(parts)
