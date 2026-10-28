"""Ręczne dodanie oferty (python main.py --add --url <link> [--text "<opis>"]), np. z posta albo z telefonu.

Bez filtrów (dodajemy świadomie), ale z dedupem i ATS. Źródło = "ręcznie". Tekst podany przez użytkownika jest opisem;
bez niego próbujemy pobrać stronę (bez logowania: LinkedIn przez publiczny endpoint "guest", reszta przez JSON-LD / og:title).
Gdy pobranie się nie uda, oferta i tak trafia do arkusza z linkiem i notatką "Uzupełnij opis ręcznie".
"""
import hashlib
import html
import re
from urllib.parse import urlsplit

from models import Offer
from sources import linkedin
from sources.htmlutil import clean_text, job_posting, job_posting_description, page_text

SOURCE = "ręcznie"
BROWSER_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/130.0 Safari/537.36"
_LI_ID = re.compile(r"linkedin\.com/(?:comm/)?jobs/view/(?:[^/?#]*-)?(\d{6,})|currentJobId=(\d{6,})")
_LI_TITLE = re.compile(r'top-card-layout__title[^>]*>\s*(.*?)\s*</h[12]>', re.S)
_LI_COMPANY = re.compile(r'topcard__org-name-link[^>]*>\s*(.*?)\s*</a>', re.S)
_OG_TITLE = re.compile(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']*)', re.I)
_TITLE_TAG = re.compile(r"<title[^>]*>(.*?)</title>", re.S | re.I)


def canonical(url: str) -> str:
    """Link bez parametrów śledzących i fragmentu (LinkedIn: zawsze /jobs/view/<id>)."""
    m = _LI_ID.search(url or "")
    if m:
        return linkedin.OFFER_URL.format(id=m.group(1) or m.group(2))
    p = urlsplit((url or "").strip())
    return f"{p.scheme}://{p.netloc.lower()}{p.path.rstrip('/')}" + (f"?{p.query}" if p.query and "utm_" not in p.query else "")


def _clean(s: str) -> str:
    return clean_text(html.unescape(s or ""))


def parse_page(url: str, page: str) -> dict:
    """title, company, description, employment z pobranej strony; brakujące pola są puste."""
    if _LI_ID.search(url):
        text, criteria = linkedin.parse_detail(page)
        t, c = _LI_TITLE.search(page), _LI_COMPANY.search(page)
        etype = criteria.get("Employment type") or criteria.get("Rodzaj zatrudnienia") or ""
        return {"title": _clean(t.group(1)) if t else "", "company": _clean(c.group(1)) if c else "",
                "description": text, "employment": [etype] if etype else []}
    node = job_posting(page) or {}
    org = node.get("hiringOrganization")
    company = (org.get("name") if isinstance(org, dict) else org) or ""
    title = node.get("title") or ""
    if not title:
        m = _OG_TITLE.search(page) or _TITLE_TAG.search(page)
        title = m.group(1) if m else ""
    return {"title": _clean(str(title)), "company": _clean(str(company)),
            "description": job_posting_description(page) or page_text(page)[:20000], "employment": []}


def fetch_meta(session, url: str) -> dict:
    """Pobranie strony bez logowania; każdy błąd (sieć, 403, challenge) = pusty wynik."""
    m = _LI_ID.search(url)
    target = linkedin.DETAIL_URL.format(id=m.group(1) or m.group(2)) if m else url
    try:
        r = session.get(target, headers={"User-Agent": BROWSER_UA, "Accept": "text/html", "Accept-Language": "pl-PL,pl;q=0.9"},
                        timeout=30)
        if r.status_code >= 400 or "Just a moment" in r.text[:3000]:
            return {}
        return parse_page(url, r.text)
    except Exception:
        return {}


def build_offer(session, url: str | None, text: str | None) -> tuple[Offer, list[str]]:
    """(oferta, dodatkowe notatki)."""
    url, text = (url or "").strip(), (text or "").strip()
    link = canonical(url) if url else ""
    meta = fetch_meta(session, url) if url else {}
    description = text or meta.get("description") or ""
    notes = []
    if not meta.get("title") or not meta.get("company"):
        notes.append("Uzupełnij firmę i stanowisko")
    if not description:
        notes.append("Uzupełnij opis ręcznie")
    host = urlsplit(link).netloc or "bez linku"
    ident = hashlib.sha1((link or text).encode("utf-8")).hexdigest()[:12]
    offer = Offer(source=SOURCE, source_id=ident, url=link,
                  company=meta.get("company") or "?", title=meta.get("title") or f"(do uzupełnienia) {host}",
                  remote=None, employment=meta.get("employment") or [], description=description)
    return offer, notes
