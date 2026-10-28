"""Kolumna "Wymiar": "Pełny etat", "Część etatu (1/2)", "Zlecenie / kontrakt" albo pusto (brak informacji).

Sygnały: pole portalu (Offer.employment, np. "part_time", "freelance", "Contract", "full_time") i tekst tytułu + opisu
(1/4, 1/2, "N h/tydz.", part-time, zlecenie, freelance, pełny etat). Część etatu i zlecenia omijają próg minimalnych
widełek, bo stawka za część etatu jest z natury niższa.
"""
import re
import unicodedata

FULL = "Pełny etat"
PART = "Część etatu"
GIG = "Zlecenie / kontrakt"
PORTAL_FULL = {"full_time", "full-time", "fulltime"}
PORTAL_PART = {"part_time", "part-time", "parttime"}
PORTAL_GIG = {"freelance", "contract", "temporary", "zlecenie", "contractor"}
MAX_PART_HOURS = 30            # od tylu godzin tygodniowo nie jest to już "część etatu"

_FRACTION = re.compile(r"(?<!\d)(\d)\s*/\s*(\d)\s*(?:etat\w*|fte|time|full)")
_PART_TEXT = re.compile(r"part[ -]?time|pol etatu|polowa etatu|cwierc etatu|czesc etatu|niepelny wymiar|niepelnym wymiarze|"
                        r"niepelnego wymiaru")
_HOURS = re.compile(r"(?<!\d)(\d{1,2})\s*(?:h|godz\w*|hours?)(?:\s*(?:/|per|w|na|a)\s*|\s+)(?:tyd\w*|tyg\w*|week)")
_FULL_TEXT = re.compile(r"pelny etat|pelnym wymiarze|pelnego wymiaru|full[ -]?time")
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


def value(portal, title: str, description: str) -> str:
    """Wartość komórki Wymiar. Część etatu i zlecenie wygrywają z "Pełny etat" (np. "full-time lub part-time")."""
    found = labels(portal, title, description)
    if found:
        return " + ".join(found)
    raw = {str(p).strip().lower() for p in portal or []}
    return FULL if raw & PORTAL_FULL or _FULL_TEXT.search(_fold(f"{title} {description}")) else ""
