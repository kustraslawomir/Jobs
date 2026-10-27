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
# tylko oznaczenia płci/formy w nawiasach, np. (m/f), (k/m), (f/m/d), (m/w/d), (remote); technologie zostają
_PAREN_NOISE = re.compile(r"\(\s*(?:[mfkwdx](?:\s*[/,|]\s*[mfkwdx])*|remote|zdalnie)\s*\)")
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
    s = _PAREN_NOISE.sub(" ", s)
    s = _TITLE_NOISE.sub(" ", s)
    return _SP.sub(" ", _NON.sub(" ", s)).strip()


def looks_like_agency(company: str) -> bool:
    c = (company or "").lower()
    return any(h in c for h in AGENCY_HINTS)


SAME_SOURCE = "duplikat w tym samym źródle"
OTHER_SOURCE = "duplikat z innego portalu / już w arkuszu"


class Deduper:
    def __init__(self, existing: list[tuple[str, str, str]], threshold: int = 90):
        """existing: [(klucz, firma, stanowisko), ...] z arkusza."""
        self.threshold = threshold
        self.keys = {k for k, _, _ in existing if k}
        # firma -> [(znormalizowany tytuł, oryginalny tytuł, źródło, czy z arkusza)]
        self.by_company: dict[str, list[tuple[str, str, str, bool]]] = {}
        for key, comp, title in existing:
            self._remember(comp, title, key.split(":", 1)[0], True)

    def _remember(self, company, title, source, from_sheet):
        self.by_company.setdefault(norm_company(company), []).append(
            (norm_title(title), title, source, from_sheet))

    def check(self, offer) -> tuple[str, str | None, int | None] | None:
        """None = nowa oferta. Inaczej (powód, tytuł z którym się zmatchował, score)."""
        if offer.key in self.keys:
            return "to samo ID", None, None
        t = norm_title(offer.title)
        for other, raw, source, from_sheet in self.by_company.get(norm_company(offer.company), []):
            score = fuzz.token_sort_ratio(t, other)
            if score >= self.threshold:
                same = source == offer.source and not from_sheet
                return (SAME_SOURCE if same else OTHER_SOURCE), raw, round(score)
        return None

    def add(self, offer):
        self.keys.add(offer.key)
        self._remember(offer.company, offer.title, offer.source, False)
