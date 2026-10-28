"""Historia widzianych ofert (zakładka _widziane): wiek ogłoszeń, odświeżenia i znikanie ("ghost joby").

Wiersz historii = jedno wystąpienie oferty w jednym źródle (klucz_źródła = Offer.key), przypisane do klucza kanonicznego,
czyli Klucza wiersza w Ofertach, z którym się zmatchowało (także gdy dedup odrzucił je jako duplikat).
Wiek grupy liczy arkusz formułą: dziś minus najwcześniejsza data z całej grupy (kolumna najwcześniejsza_data).
Oferta znika dopiero, gdy każde jej "liczące się" źródło miało MISS_LIMIT udanych runów z rzędu bez niej;
źródło z błędem albo nieuruchomione nie zmienia nic. Źródła z oknem czasowym (np. LinkedIn: ostatnie 30 dni)
i oferty dodane ręcznie nie mogą "zniknąć" (config: ghost.no_disappearance).
"""
import datetime as dt
import re
from dataclasses import dataclass

HEADERS = ["klucz_kanoniczny", "źródło", "klucz_źródła", "data_publikacji_z_portalu", "pierwszy_raz_widziana",
           "ostatnio_widziana", "liczba_odświeżeń", "najnowsza_data_portalu", "nieobecne_runy", "najwcześniejsza_data"]
MISS_LIMIT = 3          # tyle udanych runów źródła z rzędu bez oferty = oferta zniknęła
_EPOCH = dt.date(1899, 12, 30)       # początek numeracji dat w Arkuszach Google
_ISO = re.compile(r"^(\d{4})-(\d{2})-(\d{2})")
_DMY = re.compile(r"^(\d{1,2})[./](\d{1,2})[./](\d{4})")
TOKEN_RX = re.compile(r"Odświeżana \d+×\.?|Wisi na \d+ portalach\.?")


def iso_date(value) -> str:
    """Data jako RRRR-MM-DD z: epoch ms / s, ISO ('2026-10-28T06:40:11Z', '...+01:00'), RRRR-MM-DD, DD.MM.RRRR; błąd = ''."""
    if value in (None, ""):
        return ""
    try:
        if isinstance(value, (int, float)) or re.fullmatch(r"\d{9,13}(\.\d+)?", str(value).strip()):
            n = float(value)
            return dt.datetime.fromtimestamp(n / 1000 if n > 1e11 else n, dt.timezone.utc).date().isoformat()
        s = str(value).strip()
        if m := _ISO.match(s):
            return dt.date(int(m[1]), int(m[2]), int(m[3])).isoformat()
        if m := _DMY.match(s):
            return dt.date(int(m[3]), int(m[2]), int(m[1])).isoformat()
    except (ValueError, OverflowError, OSError):
        pass
    return ""


def serial(day: str) -> int | str:
    d = iso_date(day)
    return (dt.date.fromisoformat(d) - _EPOCH).days if d else ""


@dataclass
class Seen:
    canonical: str
    source: str
    key: str
    published: str = ""        # najwcześniejsza data publikacji podana przez portal
    first_seen: str = ""
    last_seen: str = ""
    refreshes: int = 0
    latest: str = ""           # najnowsza data podana przez portal (do wykrywania odświeżeń)
    missed: int = 0            # kolejne udane runy źródła bez tej oferty

    def earliest(self) -> str:
        return min((d for d in (self.published, self.first_seen) if d), default="")

    def to_row(self) -> list:
        return [self.canonical, self.source, self.key, self.published, self.first_seen, self.last_seen,
                self.refreshes, self.latest, self.missed, serial(self.earliest())]

    @classmethod
    def from_row(cls, r: list) -> "Seen | None":
        r = list(r) + [""] * len(HEADERS)
        if not (r[0] and r[2]):
            return None
        num = lambda v: int(v) if str(v).strip().isdigit() else 0          # noqa: E731
        return cls(r[0], r[1], r[2], iso_date(r[3]), iso_date(r[4]), iso_date(r[5]), num(r[6]), iso_date(r[7]), num(r[8]))


@dataclass
class Summary:
    earliest: str
    refreshes: int
    portals: int
    disappeared: bool


class History:
    def __init__(self, rows=()):
        self.by_key: dict[str, Seen] = {r.key: r for r in rows}

    def canonical_of(self, key: str) -> str | None:
        r = self.by_key.get(key)
        return r.canonical if r else None

    def record(self, o, canonical: str, today: str):
        """Zapisuje wystąpienie oferty `o` w tym runie. Data publikacji zostaje najwcześniejsza; nowsza data z portalu
        niż zapisana = odświeżenie (+1). Pierwsza obserwacja z datą odświeżenia późniejszą niż publikacji liczy się jako 1."""
        pub = getattr(o, "published", "") or ""
        new = getattr(o, "renewed", "") or pub
        r = self.by_key.get(o.key)
        if r is None:
            r = self.by_key[o.key] = Seen(canonical, o.source, o.key, first_seen=today)
        r.last_seen, r.missed = today, 0
        if pub and (not r.published or pub < r.published):
            r.published = pub
        if not r.published and new:
            r.published = new
        if new:
            if not r.latest:
                r.latest = new
                if r.published and new > r.published:
                    r.refreshes += 1
            elif new > r.latest:
                r.refreshes += 1
                r.latest = new

    def mark_runs(self, returned: dict[str, set[str]]):
        """returned: źródło -> klucze zwrócone w UDANYM runie tego źródła. Tylko te źródła zwiększają licznik nieobecności."""
        for r in self.by_key.values():
            keys = returned.get(r.source)
            if keys is not None and r.key not in keys:
                r.missed += 1

    def groups(self) -> dict[str, list[Seen]]:
        out: dict[str, list[Seen]] = {}
        for r in self.by_key.values():
            out.setdefault(r.canonical, []).append(r)
        return out

    @staticmethod
    def summarize(rows: list[Seen], no_disappearance=()) -> Summary:
        alive = [r for r in rows if r.missed < MISS_LIMIT]
        counted = [r for r in rows if r.source not in set(no_disappearance)]
        gone = bool(counted) and all(r.missed >= MISS_LIMIT for r in counted)
        return Summary(min((r.earliest() for r in rows if r.earliest()), default=""), sum(r.refreshes for r in rows),
                       len({r.source for r in alive}), gone)

    def summaries(self, no_disappearance=()) -> dict[str, Summary]:
        return {c: self.summarize(rows, no_disappearance) for c, rows in self.groups().items()}

    def rows(self) -> list[list]:
        return [r.to_row() for r in self.by_key.values()]


def active_value(s: Summary, current: str, today: str) -> str:
    """"Tak" albo "Zniknęła RRRR-MM-DD" (data pierwszego wykrycia zostaje przy kolejnych runach)."""
    if not s.disappeared:
        return "Tak"
    if (current or "").startswith("Zniknęła"):
        return current
    return f"Zniknęła {today}"


def tokens(s: Summary) -> list[str]:
    out = []
    if s.refreshes >= 2:
        out.append(f"Odświeżana {s.refreshes}×")
    if s.portals >= 3:
        out.append(f"Wisi na {s.portals} portalach")
    return out


def merge_note(existing: str, toks: list[str]) -> str:
    """Dopisuje tokeny do Notatek bez ruszania reszty; stare wartości tych samych tokenów są podmieniane."""
    parts = [p for p in re.split(r"\.\s+", (existing or "").strip()) if p and not TOKEN_RX.fullmatch(p.strip())]
    return ". ".join(parts + toks)
