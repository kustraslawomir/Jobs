"""ATS match: ta sama logika co w arkuszu Excel, tylko w Pythonie.

Słownik skilli (keyword + do 3 wariantów, Mam?, waga) czytany z zakładki "Słownik"
w Google Sheets. Szuka całych słów w znormalizowanym opisie oferty.
"""
import re

_PUNCT = re.compile(r"[\n\r\t ,.;:()/\\\-!?\"'\[\]{}•|*–—<>&+#’`]")
_SPACES = re.compile(r"\s+")

MIN_REQUIREMENTS = 3   # poniżej tej liczby rozpoznanych wymagań match nie jest wiarygodny

SCORE = {"tak": 1.0, "częściowo": 0.5}


def norm(text: str) -> str:
    t = _PUNCT.sub(" ", (text or "").lower())
    return " " + _SPACES.sub(" ", t).strip() + " "


class Skill:
    def __init__(self, keyword, variants, mam, weight):
        self.keyword = keyword.strip()
        self.terms = [norm(v) for v in [keyword, *variants] if v and v.strip()]
        self.mam = (mam or "").strip()
        self.score = SCORE.get(self.mam.lower(), 0.0)
        try:
            self.weight = float(weight)
        except (TypeError, ValueError):
            self.weight = 1.0

    def found_in(self, normalized: str) -> bool:
        return any(t in normalized for t in self.terms)


def load_skills(rows: list[list[str]]) -> list[Skill]:
    """rows: wiersze z arkusza bez nagłówka: kategoria, keyword, w2, w3, w4, mam, waga, ..."""
    out = []
    for r in rows:
        r = (r + [""] * 8)[:8]
        if r[1].strip():
            out.append(Skill(r[1], r[2:5], r[5], r[6]))
    return out


def evaluate(description: str, skills: list[Skill], cv_text: str):
    """Zwraca (match 0-1 albo None, luki, masz-ale-nie-ma-w-CV, liczba rozpoznanych wymagań)."""
    d, cv = norm(description), norm(cv_text)
    found = [s for s in skills if s.found_in(d)]
    total = sum(s.weight for s in found)
    if len(found) < MIN_REQUIREMENTS or not total:
        return None, [], [], len(found)
    match = sum(s.weight * s.score for s in found) / total
    gaps = []
    for s in found:
        if s.score < 1:
            suffix = {"Częściowo": " (częściowo)", "Do weryfikacji": " (?)"}.get(s.mam, "")
            gaps.append(s.keyword + suffix)
    add_to_cv = [s.keyword for s in found if s.score == 1 and not s.found_in(cv)]
    return match, gaps, add_to_cv, len(found)
