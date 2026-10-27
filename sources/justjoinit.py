"""JustJoinIT. Kategoria "android", najnowsze najpierw.

DO WERYFIKACJI w DevTools: LIST_URL, nagłówki i nazwy pól w odpowiedzi.
"""
import time
from models import Offer

LIST_URL = "https://api.justjoin.it/v2/user-panel/offers"
PARAMS = {"categories[]": "android", "sortBy": "published", "orderBy": "DESC", "perPage": 100}
HEADERS = {"Version": "2"}
OFFER_URL = "https://justjoin.it/job-offer/{slug}"
MAX_PAGES = 3


def _salary(item):
    from . import pick
    best = None
    for et in pick(item, "employmentTypes", default=[]) or []:
        if pick(et, "to") is None:
            continue
        if best is None or (pick(et, "type", default="").lower() == "b2b"):
            best = et
    if not best:
        return None, None, "", "month", ""
    unit = str(pick(best, "unit", default="month")).lower()
    period = "hour" if "hour" in unit else "year" if "year" in unit else "month"
    typ = str(pick(best, "type", default="")).lower()
    contract = {"b2b": "B2B", "permanent": "UoP", "mandate_contract": "UZ"}.get(typ, typ)
    return pick(best, "from"), pick(best, "to"), str(pick(best, "currency", default="")).upper(), period, contract


def fetch(session) -> list[Offer]:
    from . import pick
    out = []
    for page in range(1, MAX_PAGES + 1):
        r = session.get(LIST_URL, params={**PARAMS, "page": page}, headers=HEADERS, timeout=30)
        r.raise_for_status()
        data = r.json()
        items = pick(data, "data", default=[]) or []
        for it in items:
            slug = pick(it, "slug", "id")
            if not slug:
                continue
            sf, st, cur, per, con = _salary(it)
            skills = pick(it, "requiredSkills", "skills", default=[]) or []
            skills = [s if isinstance(s, str) else pick(s, "name", default="") for s in skills]
            wt = str(pick(it, "workplaceType", default="")).lower()
            out.append(Offer(
                source="justjoinit", source_id=str(slug), url=OFFER_URL.format(slug=slug),
                company=pick(it, "companyName", default="?"), title=pick(it, "title", default="?"),
                remote=(wt == "remote") if wt else None, location=pick(it, "city", default=""),
                salary_from=sf, salary_to=st, currency=cur, salary_period=per, contract=con,
                # lista na start; pełny opis dociąga main.py przez fetch_details (jeśli włączone)
                description=" ".join([pick(it, "title", default="")] + skills),
            ))
        total_pages = pick(data, "meta.totalPages", default=1)
        if page >= total_pages or not items:
            break
        time.sleep(1.5)
    return out
