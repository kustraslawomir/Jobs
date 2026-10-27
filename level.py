"""Ocena poziomu stanowiska: "Mid" | "Senior" | "Senior+" | "?".

Sygnały, w tej kolejności (konflikt = wyższy poziom):
  a) pole seniority / experienceLevel z API portalu (Offer.seniority),
  b) tytuł: mid / regular -> Mid, senior -> Senior,
  c) wymagane lata w opisie: <= years_mid_max -> Mid, <= years_senior_max -> Senior, więcej -> Senior+,
  d) sygnały podbijające Senior -> Senior+ (config.yaml: level.bump_signals, regexy).
Brak sygnałów a-c = "?". Tekst jest normalizowany jak opisy w zakładce _opisy (małe litery, bez ogonków,
bez interpunkcji), więc te same reguły działają na świeżym opisie i na opisie zapisanym w arkuszu.
"""
import re
from dataclasses import dataclass, field

from dedup import _ascii

MID, SENIOR, SENIOR_PLUS, UNKNOWN = "Mid", "Senior", "Senior+", "?"
LEVELS = [MID, SENIOR, SENIOR_PLUS, UNKNOWN]
_RANK = {MID: 1, SENIOR: 2, SENIOR_PLUS: 3}

# wartości pól poziomu zwracane przez portale (sprawdzone na żywych odpowiedziach 2026-10-27):
#   JJIT experienceLevel: junior | mid | senior;  NFJ seniority (lista): Junior | Mid | Senior | Lead | Expert;
#   SOLID.Jobs experienceLevel: Intern | Junior | Regular | Senior;  Bulldogjob experienceLevel: junior | medium | senior | lead;
#   czyjesteldorado seniority: intern | junior | mid | senior | c_level | other.
# Junior / Intern / other nie niosą informacji o poziomie docelowym (oferty juniorskie odsiewa filtr tytułów).
PORTAL_LEVELS = {"mid": MID, "medium": MID, "regular": MID, "senior": SENIOR,
                 "lead": SENIOR_PLUS, "expert": SENIOR_PLUS, "c_level": SENIOR_PLUS}

_TITLE_WORDS = [(re.compile(r"(?<![a-z0-9])(mid|middle|regular)(?![a-z0-9])"), MID),
                (re.compile(r"(?<![a-z0-9])(senior|sr)(?![a-z0-9])"), SENIOR)]
_RANGE = re.compile(r"(\d)\s*[-–]\s*(\d)")
_NON = re.compile(r"[^a-z0-9 ]+")
_SP = re.compile(r"\s+")
_YEARS = re.compile(r"(?<![0-9])(\d{1,2})(?: to \d{1,2})? (?:years?|yrs?|lat|lata)(?![a-z])")
_NOT_REQUIREMENT_AFTER = re.compile(r"^ (?:ago|old|on the market|of history|of operation|in business|na rynku|temu)")
_NOT_REQUIREMENT_BEFORE = re.compile(r"(?:last|past|over the|ostatni\w*|since|founded) $")
MAX_YEARS = 20


def normalize(text: str) -> str:
    t = _RANGE.sub(r"\1 to \2", (text or "").lower())      # przed foldem: myślnik "–" znika przy konwersji do ASCII
    t = _ascii(t)
    return _SP.sub(" ", _NON.sub(" ", t)).strip()


def years_required(text: str) -> int | None:
    """Największa liczba lat doświadczenia wymagana w opisie ("5+ years", "min. 6 lat", "at least 7 years", "3-5 lat" -> 3);
    pomija zdania o firmie ("20 lat na rynku") i o ostatnich latach ("last 5 years")."""
    t = f" {normalize(text)} "
    found = []
    for m in _YEARS.finditer(t):
        n = int(m.group(1))
        if not 0 < n <= MAX_YEARS:
            continue
        if _NOT_REQUIREMENT_AFTER.match(t[m.end():m.end() + 24]) or _NOT_REQUIREMENT_BEFORE.search(t[max(0, m.start() - 16):m.start()]):
            continue
        found.append(n)
    return max(found) if found else None


@dataclass
class Assessment:
    level: str = UNKNOWN
    reasons: list[str] = field(default_factory=list)

    @property
    def note(self) -> str:
        return f"Poziom: {', '.join(self.reasons)}" if self.reasons else ""


def _higher(a: str | None, b: str | None) -> str | None:
    return max((x for x in (a, b) if x), key=_RANK.get, default=None)


def from_portal(values) -> tuple[str | None, list[str]]:
    levels, raw = [], []
    for v in values or []:
        lvl = PORTAL_LEVELS.get(str(v).strip().lower())
        if lvl:
            levels.append(lvl)
            raw.append(str(v).strip().lower())
    return max(levels, key=_RANK.get, default=None), raw


def from_title(title: str) -> tuple[str | None, list[str]]:
    t = normalize(title)
    hits = [(lvl, m.group(1)) for rx, lvl in _TITLE_WORDS for m in rx.finditer(t)]
    return max((l for l, _ in hits), key=_RANK.get, default=None), [w for _, w in hits]


def from_years(n: int | None, cfg: dict) -> str | None:
    if n is None:
        return None
    return MID if n <= cfg["years_mid_max"] else SENIOR if n <= cfg["years_senior_max"] else SENIOR_PLUS


def bump_signals(text: str, cfg: dict) -> list[str]:
    """Etykiety sygnałów z level.bump_signals, których którykolwiek regex pasuje do znormalizowanego tekstu."""
    t = f" {normalize(text)} "
    return [label for label, patterns in cfg["bump_signals"].items()
            if any(re.search(p, t) for p in patterns)]


def assess(title: str, description: str, portal, cfg: dict) -> Assessment:
    """cfg = sekcja `level` z config.yaml. portal = wartości pól seniority z API źródła (lista albo pusta)."""
    reasons, level = [], None
    lvl, raw = from_portal(portal)
    if lvl:
        reasons.append(f"portal {'/'.join(dict.fromkeys(raw))}")
        level = lvl
    lvl, words = from_title(title)
    if lvl:
        reasons.append(f"tytuł {'/'.join(dict.fromkeys(words))}")
        level = _higher(level, lvl)
    years = years_required(f"{title} {description}")
    lvl = from_years(years, cfg)
    if lvl:
        reasons.append(f"{years}+ lat")
        level = _higher(level, lvl)
    if level is None:
        return Assessment()
    if level in (SENIOR, SENIOR_PLUS):                       # sygnały podbijają Senior; przy Senior+ tylko tłumaczą ocenę
        signals = bump_signals(f"{title} {description}", cfg)
        if signals:
            level = SENIOR_PLUS
            reasons += signals
    return Assessment(level, reasons)
