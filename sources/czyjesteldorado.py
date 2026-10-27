"""czyjesteldorado.pl – agregator ofert IT (m.in. theprotocol.it, nofluffjobs, SOLID.Jobs, bezpośrednio od firm).

Metoda: dane osadzone w HTML (payload RSC Next.js, `"jobs":[{...}]`) na stronie wyszukiwania
  GET https://czyjesteldorado.pl/search?q=android&page=N        (100 ofert na stronę, ~5 stron; strony za
                                                                   ostatnią powtarzają ostatnią)
Zweryfikowane 2026-10-27. robots.txt zabrania tylko /api/ i /redirect/, więc używamy wyłącznie stron HTML
(NIE wewnętrznego API); linkujemy do strony oferty /praca/{id}-{slug}, nie do /redirect/.
Filtra remote po stronie serwera nie ma (parametry workMode/p są ignorowane): remote bierzemy z `workModes`.
Widełki: salary[] per forma z `period` (month/hour/day); przeliczamy na miesiąc, jak w JJIT.
Pełny opis: JSON-LD JobPosting ze strony oferty (details()).
"""
import time
from models import Offer, Pay
from contracts import normalize
from .htmlutil import array_after, job_posting_description, next_flight, page_text

SEARCH_URL = "https://czyjesteldorado.pl/search"
OFFER_URL = "https://czyjesteldorado.pl/praca/{id}-{slug}"
QUERIES = ["android", "kotlin"]
MAX_PAGES = 6
PER_PAGE = 100
MONTH_HOURS, MONTH_DAYS = 168, 21


def parse_search(page: str) -> list[dict]:
    return array_after(next_flight(page), '"jobs":[')


def _pay(item: dict) -> tuple[list[str], list[Pay]]:
    contracts = [c for c in map(normalize, item.get("contractTypes") or []) if c]
    pays = []
    for s in item.get("salary") or []:
        name, lo, hi = normalize(s.get("contractType")), s.get("min"), s.get("max")
        if lo is None and hi is None:
            continue
        period, hourly = s.get("period"), None
        mult = {"hour": MONTH_HOURS, "day": MONTH_DAYS}.get(period, 1)
        if period == "hour":
            hourly = (lo if lo is not None else hi, hi if hi is not None else lo)
        pays.append(Pay(name, lo * mult if lo is not None else None, hi * mult if hi is not None else None,
                        str(s.get("currency") or "PLN").upper(), hourly))
    return contracts, pays


def to_offer(item: dict) -> Offer | None:
    from . import pick
    oid, slug = pick(item, "id"), pick(item, "slug")
    if not oid or not slug:
        return None
    modes = item.get("workModes") or []
    remote = True if (item.get("isRemote") or "remote" in modes) else (False if modes else None)
    desc = item.get("description") if isinstance(item.get("description"), dict) else {}
    texts = [t for t in (desc.get("summary"), desc.get("about")) if isinstance(t, str) and not t.startswith("$")]
    contracts, pays = _pay(item)
    return Offer(
        source="czyjesteldorado", source_id=str(oid), url=OFFER_URL.format(id=oid, slug=slug),
        company=pick(item, "company.name", default="?"), title=pick(item, "title", default="?"),
        remote=remote, location=", ".join(item.get("cities") or []),
        contract=contracts, pay=pays,
        description=" ".join([pick(item, "title", default="")] + list(item.get("keywords") or []) + texts),
    )


def fetch(session) -> list[Offer]:
    out, seen = [], set()
    for q in QUERIES:
        prev = None
        for page in range(1, MAX_PAGES + 1):
            r = session.get(SEARCH_URL, params={"q": q, "page": page}, timeout=30)
            r.raise_for_status()
            items = parse_search(r.text)
            ids = [i.get("id") for i in items]
            if not items or ids[:3] == prev:                    # strona za ostatnią powtarza ostatnią
                break
            prev = ids[:3]
            for it in items:
                o = to_offer(it)
                if o and o.source_id not in seen:
                    seen.add(o.source_id)
                    out.append(o)
            if len(items) < PER_PAGE:
                break
            time.sleep(1.5)
    return out


def details(session, offer: Offer) -> str:
    """Pełny opis do ATS: tytuł + skille z listy + tekst z JSON-LD strony oferty."""
    r = session.get(offer.url, headers={"Accept": "text/html"}, timeout=30)
    r.raise_for_status()
    text = job_posting_description(r.text) or page_text(r.text)
    time.sleep(1.5)
    return f"{offer.description} {text}"
