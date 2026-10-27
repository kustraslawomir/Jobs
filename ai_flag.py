"""Oznaczanie ofert związanych z AI (kolumna "AI").

Dwie listy w config.yaml (`ai.produkt`, `ai.workflow`), dopasowywane do tytułu i opisu po normalizacji jak opisy
w zakładce _opisy (małe litery, bez ogonków i interpunkcji: "AI-assisted" to "ai assisted"). Wpis to regex
dopasowywany jako całe słowo (z opcjonalnym "s" na końcu), więc "ai" nie łapie się w środku wyrazów.
Wartość komórki: "produkt", "workflow" albo "produkt + workflow" i w nawiasie maksymalnie 3 trafione słowa;
brak trafień = pusty tekst.
"""
import re

from level import normalize

MAX_WORDS = 3
_CATEGORIES = ("produkt", "workflow")


def hits(text: str, patterns: list[str]) -> list[str]:
    """Trafienia w kolejności wpisów na liście (każdy wpis raz, tekstem znalezionym w ofercie)."""
    t = f" {normalize(text)} "
    out = []
    for p in patterns:
        m = re.search(rf"(?<![a-z0-9])(?:{p})s?(?![a-z0-9])", t)
        if m and m.group(0) not in out:
            out.append(m.group(0))
    return out


def detect(title: str, description: str, cfg: dict) -> str:
    """cfg = sekcja `ai` z config.yaml."""
    text = f"{title} {description}"
    found = {c: hits(text, cfg.get(c) or []) for c in _CATEGORIES}
    # "claude" w "claude code", "ai" w "ai tools" to to samo trafienie: liczymy je tylko jako workflow
    found["produkt"] = [h for h in found["produkt"]
                        if not any(f" {h} " in f" {w} " for w in found["workflow"] if w != h)]
    cats = [c for c in _CATEGORIES if found[c]]
    if not cats:
        return ""
    words = []                                   # na przemian z obu list, żeby w nawiasie były oba rodzaje trafień
    for i in range(MAX_WORDS):
        for c in cats:
            if i < len(found[c]) and len(words) < MAX_WORDS:
                words.append(found[c][i])
    return f"{' + '.join(cats)} ({', '.join(words)})"


def only_bare_ai(value: str, title: str, description: str, cfg: dict) -> bool:
    """Czy jedynym trafieniem jest samo słowo "ai" (do ręcznego przeglądu fałszywych alarmów)."""
    text = f"{title} {description}"
    return bool(value) and all(h == "ai" for c in _CATEGORIES for h in hits(text, cfg.get(c) or []))
