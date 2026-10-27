"""Deduplikacja ofert: ID -> (filtry, opis) -> treść + tytuł + firma.

1. Ten sam portal i ID: klucz source:id (kolumna "Klucz" w arkuszu).
2. Treść + tytuł + firma, wobec ofert z arkusza i z tego samego runu:
   - treść: shingle 5-słowne na znormalizowanym opisie, podobieństwo Jaccarda,
   - tytuł: fuzz.token_sort_ratio na tytułach po normalizacji (PL->EN, developer == engineer,
     bez nawiasów i oznaczeń płci, bez słów typu senior/lead),
   - firma: bez form prawnych i końcówek (systems, software, ...); ta sama przy ratio >= 92
     albo gdy jedna nazwa jest pełnym prefiksem drugiej (min. 4 znaki).
   Pewny duplikat -> odrzucamy. Możliwy duplikat i oferta agencji -> zostaje, z notatką.
   Dwie oferty z rozłącznymi widełkami to dwa różne wakaty, nigdy duplikat.
3. Agencje: oferta agencji, której treść pasuje do oferty innej firmy, nie jest odrzucana.

Boilerplate ("o nas", benefity): ta sama firma wkleja ten sam akapit do każdej oferty, więc
dwie różne oferty jednej firmy mają wysokie Jaccard mimo różnych ról. Zamiast wydzielać sekcję
"wymagania" (każdy portal oddaje opis inaczej: NFJ strukturalnie, JJIT jako płaski tekst, więc
nie da się tego zrobić stabilnie) liczymy per firma, w ilu znanych ofertach (arkusz + ten run
+ porównywana oferta) występuje dany shingle. Shingle obecny w >= 3 ofertach firmy jest
boilerplate'em i wypada z obu zbiorów przed liczeniem Jaccarda. Jeśli po wycięciu zostaje
mniej niż 5 shingli, wracamy do porównania bez wycinania.
"""
import re
import unicodedata
from collections import Counter
from dataclasses import dataclass, field
from rapidfuzz import fuzz

_LEGAL = re.compile(r"\b(sp\.? ?z ?o\.? ?o\.?|s\.? ?a\.?|sp\.? ?k\.?|gmbh|ltd|inc|llc|s\.?r\.?o\.?|group|poland|polska)\b")
_COMPANY_TAIL = {"systems", "software", "technologies", "technology", "solutions", "consulting",
                 "it", "labs", "group", "poland", "polska", "europe"}
_TITLE_NOISE = re.compile(r"\b(senior|sr|mid|regular|lead|principal|staff|junior|m/f|k/m|f/m/d|m/w/d|remote|zdalnie|100%)\b")
_BRACKETS = re.compile(r"[(\[].*?[)\]]")
_PL_EN = {"programista": "developer", "inzynier": "engineer", "starszy": "senior",
          "mlodszy": "junior", "specjalista": "specialist", "engineer": "developer"}
_NON = re.compile(r"[^a-z0-9 ]+")
_SP = re.compile(r"\s+")

AGENCY_HINTS = ("recruit", "rekrut", "hr ", "talent", "hays", "antal", "michael page", "experis",
                "randstad", "sii", "connectis", "devire", "grafton", "useme", "clurgo")

MAX_DESC_CHARS = 20_000      # tyle znormalizowanego opisu trzymamy w zakładce "_opisy"
SHINGLE = 5
MIN_DESC_WORDS = 30          # krótszy opis (np. sam tytuł + skille z listy) nie nadaje się do porównań

DEFAULTS = {"title_sure": 90, "title_possible": 75, "title_content": 70,
            "content_sure": 0.90, "content_possible": 0.60, "company_ratio": 92}

SURE_BY_TITLE = "duplikat (firma i tytuł)"
SURE_BY_CONTENT = "duplikat (tylko po treści)"


def _ascii(s: str) -> str:
    s = s.replace("ł", "l").replace("Ł", "L")
    return unicodedata.normalize("NFKD", s).encode("ascii", "ignore").decode()


def company_forms(s: str) -> tuple[str, str]:
    """(base, core): bez form prawnych / dodatkowo bez końcówek typu "systems"."""
    s = _LEGAL.sub(" ", _ascii((s or "").lower()))
    base = _SP.sub(" ", _NON.sub(" ", s)).strip()
    words = base.split()
    while len(words) > 1 and words[-1] in _COMPANY_TAIL:
        words.pop()
    return base, " ".join(words)


def norm_company(s: str) -> str:
    return company_forms(s)[1]


def _full_prefix(x: str, y: str) -> bool:
    short, long_ = sorted((x, y), key=len)
    return len(short) >= 4 and (long_ == short or long_.startswith(short + " "))


def same_company(a: tuple[str, str], b: tuple[str, str], ratio: int = 92) -> bool:
    (a_base, a_core), (b_base, b_core) = a, b
    if not a_core or not b_core:
        return False
    if fuzz.ratio(a_core, b_core) >= ratio:
        return True
    return any(_full_prefix(x, y) for x, y in
               ((a_core, b_core), (a_base, b_base), (a_core, b_base), (a_base, b_core)))


def norm_title(s: str) -> str:
    s = _ascii((s or "").lower())
    s = _TITLE_NOISE.sub(" ", _BRACKETS.sub(" ", s))     # nawiasy tylko do wyświetlania, nie do porównań
    words = _SP.sub(" ", _NON.sub(" ", s)).split()
    words = [_PL_EN.get(w, w) for w in words]
    return " ".join(w for w in words if w not in ("senior", "junior"))


def norm_description(s: str) -> str:
    t = _SP.sub(" ", _NON.sub(" ", _ascii((s or "").lower()))).strip()
    return t[:MAX_DESC_CHARS]


def shingles(norm_text: str, n: int = SHINGLE) -> frozenset[str] | None:
    words = norm_text.split()
    if len(words) < MIN_DESC_WORDS:
        return None
    return frozenset(" ".join(words[i:i + n]) for i in range(len(words) - n + 1))


def jaccard(a: frozenset, b: frozenset) -> float:
    return len(a & b) / len(a | b) if a and b else 0.0


def looks_like_agency(company: str) -> bool:
    c = (company or "").lower()
    return any(h in c for h in AGENCY_HINTS)


_NUM = r"\d{1,3}(?:[  ]\d{3})+|\d+"
_RANGE = re.compile(rf"({_NUM})\s*[–-]\s*({_NUM})")
_CUR = re.compile(r"\b(PLN|EUR|USD|GBP|CHF)\b")


def parse_salary_text(text: str, fx: dict) -> tuple[float, float] | None:
    """Odczyt przedziału (PLN/mies.) z tekstu kolumny "Widełki / forma", np. "23 520–29 400 PLN/mies. B2B (140–175/h)"."""
    t = re.sub(r"\([^)]*\)", " ", text or "")           # stawki godzinowe w nawiasach pomijamy
    ranges = [(float(re.sub(r"\D", "", a)), float(re.sub(r"\D", "", b))) for a, b in _RANGE.findall(t)]
    if not ranges:
        return None
    cur = _CUR.search(t)
    k = fx.get(cur.group(1), 1) if cur else 1
    return min(r[0] for r in ranges) * k, max(r[1] for r in ranges) * k


def _overlap(a, b) -> bool:
    return a[0] <= b[1] and b[0] <= a[1]


@dataclass
class Match:
    kind: str                  # "dup" | "possible" | "agency"
    reason: str
    company: str
    title: str
    source: str
    content: float | None
    title_score: int

    @property
    def note(self) -> str:
        if self.kind == "agency":
            return f"Agencja – prawdopodobnie oferta {self.company}"
        c = "n/d" if self.content is None else f"{self.content:.0%}"
        return f"Możliwy duplikat: {self.company} – {self.title} ({self.source}, treść {c}, tytuł {self.title_score}%)"

    def describe(self, offer) -> str:
        c = "n/d" if self.content is None else f"{self.content:.0%}"
        return (f'"{offer.company} – {offer.title}" ({offer.source}) ~ '
                f'"{self.company} – {self.title}" ({self.source}) treść {c}, tytuł {self.title_score}%')


@dataclass
class Verdict:
    rejected: Match | None = None
    matches: list[Match] = field(default_factory=list)     # możliwe duplikaty / agencje (oferta zostaje)

    @property
    def notes(self) -> list[str]:
        return [m.note for m in self.matches]


@dataclass
class _Entry:
    key: str
    company: str
    title: str
    source: str
    forms: tuple[str, str]
    ntitle: str
    sh: frozenset | None
    salary: tuple[float, float] | None
    agency: bool


class Deduper:
    def __init__(self, existing: list[tuple], descriptions: dict[str, str] | None = None,
                 cfg: dict | None = None, fx: dict | None = None):
        """existing: [(klucz, firma, stanowisko[, widełki]), ...] z arkusza; descriptions: klucz -> znormalizowany opis."""
        self.cfg = {**DEFAULTS, **(cfg or {})}
        self.fx = fx or {}
        self.keys = set()
        self.entries: list[_Entry] = []
        self.df: dict[str, Counter] = {}                   # core firmy -> w ilu ofertach występuje shingle
        descriptions = descriptions or {}
        for row in existing:
            key, comp, title, salary_text = (tuple(row) + ("",))[:4]
            if key:
                self.keys.add(key)
            self._remember(key, comp, title, key.split(":", 1)[0], shingles(descriptions.get(key, "")),
                           parse_salary_text(salary_text, self.fx))

    def _remember(self, key, company, title, source, sh, salary):
        e = _Entry(key, company, title, source, company_forms(company), norm_title(title), sh, salary,
                   looks_like_agency(company))
        self.entries.append(e)
        if sh:
            self.df.setdefault(e.forms[1], Counter()).update(sh)

    def has_key(self, offer) -> bool:
        return offer.key in self.keys

    def _content(self, cand_sh, e: _Entry, same_co: bool) -> float | None:
        if not cand_sh or not e.sh:
            return None
        a, b = cand_sh, e.sh
        if same_co:
            df = self.df.get(e.forms[1], {})
            boiler = {s for s in a | b if df.get(s, 0) + (s in a) >= 3}
            a2, b2 = a - boiler, b - boiler
            if len(a2) >= SHINGLE and len(b2) >= SHINGLE:
                a, b = a2, b2
        return jaccard(a, b)

    def check(self, offer) -> Verdict:
        c = self.cfg
        forms, nt = company_forms(offer.company), norm_title(offer.title)
        cand_sh = shingles(norm_description(offer.description))
        salary = offer.salary_range_pln(self.fx)
        cand_agency = looks_like_agency(offer.company)
        dups, possible, agency = [], [], []

        for e in self.entries:
            same_co = same_company(forms, e.forms, c["company_ratio"])
            t = round(fuzz.token_sort_ratio(nt, e.ntitle))
            if not same_co and t < c["title_content"] and not cand_agency:
                continue
            if salary and e.salary and not _overlap(salary, e.salary):
                continue                                    # rozłączne widełki = dwa różne wakaty
            content = self._content(cand_sh, e, same_co)

            def m(kind, reason=""):
                return Match(kind, reason, e.company, e.title, e.source, content, t)

            if not same_co and cand_agency and content is not None and content >= c["content_possible"]:
                agency.append(m("agency"))
                continue
            sure_title = same_co and t >= c["title_sure"] and (content is None or content >= c["content_possible"])
            sure_content = content is not None and content >= c["content_sure"] and t >= c["title_content"]
            if sure_title or sure_content:
                if not same_co and e.agency:                # bezpośrednia oferta kontra wpis agencji: nie wycinamy
                    possible.append(m("possible"))
                else:
                    dups.append(m("dup", SURE_BY_TITLE if sure_title else SURE_BY_CONTENT))
            elif (content is not None and c["content_possible"] <= content < c["content_sure"]
                  and t >= c["title_content"]) or (same_co and c["title_possible"] <= t < c["title_sure"]):
                possible.append(m("possible"))

        def best(ms):
            return max(ms, key=lambda x: (x.content or 0, x.title_score), default=None)

        if dups:
            return Verdict(rejected=best(dups))
        return Verdict(matches=[x for x in (best(agency), best(possible)) if x])

    def add(self, offer):
        self.keys.add(offer.key)
        self._remember(offer.key, offer.company, offer.title, offer.source,
                       shingles(norm_description(offer.description)), offer.salary_range_pln(self.fx))
