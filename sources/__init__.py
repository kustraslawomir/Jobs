"""Źródła ofert. Każde źródło to funkcja fetch(session) -> list[Offer].

UWAGA: portale nie mają oficjalnego API. Endpointy i nazwy pól to ich wewnętrzne
API strony i mogą się zmienić. Gdy źródło zwróci 0 ofert albo wywali błąd:
otwórz portal w Chrome, DevTools -> Network -> Fetch/XHR, przefiltruj oferty po
Androidzie i porównaj URL i JSON z tym, co jest w pliku źródła.
"""
from . import czyjesteldorado, justjoinit, nofluffjobs

REGISTRY = {
    "justjoinit": justjoinit.fetch,
    "nofluffjobs": nofluffjobs.fetch,
    "czyjesteldorado": czyjesteldorado.fetch,
}

# opcjonalne: pełny opis do ATS, wołany tylko dla ofert po filtrach (details(session, offer) -> str)
DETAILS = {
    "justjoinit": justjoinit.details,
    "nofluffjobs": nofluffjobs.details if nofluffjobs.FETCH_DETAILS else None,
    "czyjesteldorado": czyjesteldorado.details,
}


def pick(d, *paths, default=None):
    """pick(d, "a.b", "c") -> pierwsza istniejąca ścieżka. Odporne na zmiany schematu."""
    for p in paths:
        cur = d
        ok = True
        for part in p.split("."):
            if isinstance(cur, dict) and part in cur:
                cur = cur[part]
            elif isinstance(cur, list) and part.isdigit() and int(part) < len(cur):
                cur = cur[int(part)]
            else:
                ok = False
                break
        if ok and cur not in (None, ""):
            return cur
    return default
