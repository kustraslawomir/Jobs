"""Formy współpracy: wartości z API portali -> 4 kody (B2B, UoP, UZ, UoD).

Zweryfikowane 2026-10-27 na żywych odpowiedziach:
  JJIT          employmentTypes.type: permanent, b2b, mandate_contract, any (+ specific_task_contract wg dokumentacji)
  NFJ           salary.type: b2b, permanent (+ zlecenie, uod)
  czyjesteldorado contractTypes: b2b, employment_contract, mandate_contract, internship, other
  bulldogjob    flagi contractB2b / contractEmployment / contractOther
Wartość bez treści ("any", "other" = forma nieokreślona) daje "" czyli brak informacji (oferta przechodzi filtr).
Staż dostaje kod "Staż", którego nie ma na liście dozwolonych, więc odpada. Wartości nieznane zostają w surowej
postaci (i przez to odpadają z filtra formy); main.py wypisuje je w dry-run jako "nieznana forma".
"""
import unicodedata

CODES = ("B2B", "UoP", "UZ", "UoD")
KNOWN = {*CODES, "Staż"}

_ALIASES = {
    "B2B": {"b2b", "contract b2b", "kontrakt b2b"},
    "UoP": {"permanent", "employment contract", "employment", "umowa o prace", "uop"},
    "UZ": {"mandate contract", "mandate", "zlecenie", "umowa zlecenie", "uz"},
    "UoD": {"specific task contract", "specific task", "umowa o dzielo", "o dzielo", "uod"},
    "Staż": {"internship", "intern", "staz"},
}
_LOOKUP = {alias: code for code, aliases in _ALIASES.items() for alias in aliases}
_NO_INFO = {"", "any", "other", "inne", "inna"}


def _fold(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode().lower()


def normalize(raw: str) -> str:
    """Kod formy; "" = brak informacji; nieznana wartość wraca bez zmian."""
    key = " ".join(_fold(str(raw or "")).replace("_", " ").replace("-", " ").split())
    if key in _NO_INFO:
        return ""
    return _LOOKUP.get(key, str(raw).strip())


def is_known(code: str) -> bool:
    return code in KNOWN
