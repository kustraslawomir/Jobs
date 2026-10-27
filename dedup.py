"""Deduplikacja w trzech poziomach.

1. Ten sam portal: klucz source:id (kolumna "Klucz" w arkuszu).
2. Kilka portali: znormalizowana firma + fuzzy podobieństwo tytułu.
3. Agencje: nie da się rozstrzygnąć automatycznie, więc tylko flaga w Notatkach.
"""
import re
import unicodedata
from rapidfuzz import fuzz

_LEGAL = re.compile(r"\b(sp\.? ?z ?o\.? ?o\.?|s\.? ?a\.?|sp\.? ?k\.?|gmbh|ltd|inc|llc|s\.?r\.?o\.?|group|poland|polska)\b")
_TITLE_NOISE = re.compile(r"\b(senior|sr|mid|regular|lead|principal|staff|junior|m/f|k/m|f/m/d|m/w/d|remote|zdalnie|100%)\b")
_NON = re.compile(r"[^a-z0-9 ]+")
_SP = re.compile(r"\s+")

AGENCY_HINTS = ("recruit", "rekrut", "hr ", "talent", "hays", "antal", "michael page", "experis",
                "randstad", "sii", "connectis", "devire", "grafton", "useme", "clurgo")


def _ascii(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def norm_company(s: str) -> str:
    s = _ascii((s or "").lower())
    s = _LEGAL.sub(" ", s)
    return _SP.sub(" ", _NON.sub(" ", s)).strip()


def norm_title(s: str) -> str:
    s = _ascii((s or "").lower())
    s = re.sub(r"\(.*?\)", " ", s)
    s = _TITLE_NOISE.sub(" ", s)
    return _SP.sub(" ", _NON.sub(" ", s)).strip()


def looks_like_agency(company: str) -> bool:
    c = (company or "").lower()
    return any(h in c for h in AGENCY_HINTS)


class Deduper:
    def __init__(self, existing: list[tuple[str, str, str]], threshold: int = 90):
        """existing: [(klucz, firma, stanowisko), ...] z arkusza."""
        self.threshold = threshold
        self.keys = {k for k, _, _ in existing if k}
        self.by_company: dict[str, list[str]] = {}
        for _, comp, title in existing:
            self._remember(comp, title)

    def _remember(self, company, title):
        self.by_company.setdefault(norm_company(company), []).append(norm_title(title))

    def check(self, offer) -> str | None:
        """None = nowa oferta. Inaczej powód odrzucenia."""
        if offer.key in self.keys:
            return "to samo ID"
        comp = norm_company(offer.company)
        t = norm_title(offer.title)
        for other in self.by_company.get(comp, []):
            if fuzz.token_set_ratio(t, other) >= self.threshold:
                return "ta sama firma i stanowisko (inny portal)"
        return None

    def add(self, offer):
        self.keys.add(offer.key)
        self._remember(offer.company, offer.title)
