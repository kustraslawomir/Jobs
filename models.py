from dataclasses import dataclass, field

from contracts import normalize as normalize_contract


@dataclass
class Pay:
    """Widełki dla jednej formy współpracy. lo/hi to kwoty MIESIĘCZNE w walucie oryginalnej;
    hourly = oryginalna stawka godzinowa (lo, hi), tylko dla ofert rozliczanych godzinowo."""
    contract: str
    lo: float | None
    hi: float | None
    currency: str = "PLN"
    hourly: tuple[float, float] | None = None


def _num(v: float) -> str:
    return f"{v:,.0f}".replace(",", " ")


def _span(lo, hi) -> str:
    lo, hi = round(lo) if lo is not None else None, round(hi) if hi is not None else None
    if lo is not None and hi is not None and lo == hi:
        return _num(lo)
    return f"{_num(lo) if lo is not None else '?'}–{_num(hi) if hi is not None else '?'}"


@dataclass
class Offer:
    source: str            # "justjoinit", "nofluffjobs", ...
    source_id: str         # stabilne ID z portalu
    url: str
    company: str
    title: str
    remote: bool | None = None
    location: str = ""
    salary_from: float | None = None
    salary_to: float | None = None
    currency: str = ""
    salary_period: str = "month"   # "month" | "hour" | "year"
    contract: list[str] = field(default_factory=list)   # formy współpracy: ["B2B", "UoP"]; puste = brak informacji
    pay: list[Pay] = field(default_factory=list)         # widełki per forma (tylko te z kwotami)
    description: str = ""          # pełny opis albo lista skilli, z tego liczy się ATS
    seniority: list[str] = field(default_factory=list)   # surowe pole poziomu z API portalu ("senior", "Mid"...)
    employment: list[str] = field(default_factory=list)  # surowe pola wymiaru / typu pracy z portalu ("part_time", "freelance"...)
    # wypełniane później
    match: float | None = None
    gaps: list[str] = field(default_factory=list)
    add_to_cv: list[str] = field(default_factory=list)
    n_req: int = 0                 # ile wymagań ze słownika rozpoznano w ofercie
    note: str = ""
    level: str = ""                # "Mid" | "Senior" | "Senior+" | "?" (level.py)
    ai: str = ""                   # "produkt (llm)" / "workflow (...)" / "" (ai_flag.py)
    workload: str = ""             # "Pełny etat" | "Część etatu (1/2)" | "Zlecenie / kontrakt" | "" (employment.py)

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def __post_init__(self):
        if isinstance(self.seniority, str):
            self.seniority = [self.seniority]
        self.seniority = [s for s in self.seniority if s]
        if isinstance(self.employment, str):
            self.employment = [self.employment]
        self.employment = [s for s in self.employment if s]
        if isinstance(self.contract, str):
            self.contract = [self.contract] if self.contract else []
        self.contract = list(dict.fromkeys(c for c in map(normalize_contract, self.contract) if c))
        for p in self.pay:
            p.contract = normalize_contract(p.contract)
        if not self.pay and (self.salary_from is not None or self.salary_to is not None):
            hi = self.salary_to
            mult = {"hour": 168, "year": 1 / 12}.get(self.salary_period, 1)
            self.pay = [Pay(self.contract[0] if self.contract else "",
                            self.salary_from * mult if self.salary_from else None,
                            hi * mult if hi else None, self.currency or "PLN")]
        for p in self.pay:
            if p.contract and p.contract not in self.contract:
                self.contract.append(p.contract)
        if self.salary_from is None and self.salary_to is None and self.pay:
            top = max(self.pay, key=lambda p: (p.currency == "PLN", p.hi or 0))
            self.salary_from, self.salary_to, self.currency = top.lo, top.hi, top.currency

    def salary_text(self) -> str:
        """"B2B 23 520–29 400 (140–175/h) | UoP 18 000–22 000"; kwoty miesięczne, waluta tylko gdy nie PLN."""
        parts = []
        for p in self.pay:
            seg = f"{p.contract} " if p.contract else ""
            seg += _span(p.lo, p.hi)
            if p.currency and p.currency != "PLN":
                seg += f" {p.currency}"
            if p.hourly:
                seg += f" ({_span(*p.hourly)}/h)"
            parts.append(seg)
        if parts:
            return " | ".join(parts)
        return "brak widełek" + (f" ({', '.join(self.contract)})" if self.contract else "")

    def salary_range_pln(self, fx: dict) -> tuple[float, float] | None:
        """Przedział widełek w PLN/miesiąc (suma po formach); None = brak widełek."""
        rs = [(p.lo or p.hi, p.hi or p.lo, fx.get(p.currency.upper(), 1)) for p in self.pay if p.lo or p.hi]
        if not rs:
            return None
        return min(lo * k for lo, _, k in rs), max(hi * k for _, hi, k in rs)

    def salary_to_pln_month(self, fx: dict) -> float | None:
        r = self.salary_range_pln(fx)
        return r[1] if r else None
