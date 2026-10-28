"""Wymiar pracy i zlecenia: część etatu (1/4, 1/2, "N h/tydz.", part-time) oraz zlecenia / kontrakty / freelance.

Sygnały: pole portalu (Offer.employment, np. "part_time", "freelance", "Contract") i tekst tytułu + opisu.
Wynik trafia do Notatek ("Wymiar: ..."), a oferty z takim wymiarem omijają próg minimalnych widełek,
bo stawka za część etatu jest z natury niższa.
"""
import re
import unicodedata

PART = "część etatu"
GIG = "zlecenie / kontrakt"
PORTAL_PART = {"part_time", "part-time", "parttime"}
PORTAL_GIG = {"freelance", "contract", "temporary", "zlecenie", "contractor"}
MAX_PART_HOURS = 30            # od tylu godzin tygodniowo nie jest to już "część etatu"

_FRACTION = re.compile(r"(?<!\d)(\d)\s*/\s*(\d)\s*(?:etat\w*|fte|time|full)")
_PART_TEXT = re.compile(r"part[ -]?time|pol etatu|polowa etatu|cwierc etatu|czesc etatu|niepelny wymiar|niepelnym wymiarze|"
                        r"niepelnego wymiaru")
_HOURS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:h|godz\w*|hours?)(?:\s*(?:/|per|w|na|a)\s*|\s+)(?:tyd\w*|tyg\w*|week)")
_GIG_TEXT = re.compile(r"(?<![a-z])zlecen\w*|freelanc\w*|contract basis|short[ -]term contract|project[ -]based")


def _fold(text: str) -> str:
    t = (text or "").lower().replace("ł", "l")
    return unicodedata.normalize("NFKD", t).encode("ascii", "ignore").decode()


def labels(portal, title: str, description: str) -> list[str]:
    """Lista opisów wymiaru, np. ["część etatu (1/2)", "zlecenie / kontrakt"]; pusta = zwykły pełny etat."""
    raw = {str(p).strip().lower() for p in portal or []}
    t = _fold(f"{title} {description}")
    out = []
    frac, hours = _FRACTION.search(t), _HOURS.search(t)
    detail = (f"{frac.group(1)}/{frac.group(2)}" if frac and frac.group(1) != frac.group(2) else
              f"{hours.group(1)} h/tydz." if hours and int(hours.group(1)) <= MAX_PART_HOURS else "")
    if raw & PORTAL_PART or _PART_TEXT.search(t) or detail:
        out.append(f"{PART} ({detail})" if detail else PART)
    if raw & PORTAL_GIG or _GIG_TEXT.search(t):
        out.append(GIG)
    return out


def note(portal, title: str, description: str) -> str:
    found = labels(portal, title, description)
    return f"Wymiar: {', '.join(found)}" if found else ""
