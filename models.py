from dataclasses import dataclass, field


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
    contract: str = ""             # "B2B", "UoP", ...
    description: str = ""          # pełny opis albo lista skilli, z tego liczy się ATS
    # wypełniane później
    match: float | None = None
    gaps: list[str] = field(default_factory=list)
    add_to_cv: list[str] = field(default_factory=list)
    n_req: int = 0                 # ile wymagań ze słownika rozpoznano w ofercie
    note: str = ""

    @property
    def key(self) -> str:
        return f"{self.source}:{self.source_id}"

    def salary_text(self) -> str:
        if self.salary_from is None and self.salary_to is None:
            return "brak widełek"
        f = f"{self.salary_from:,.0f}".replace(",", " ") if self.salary_from else "?"
        t = f"{self.salary_to:,.0f}".replace(",", " ") if self.salary_to else "?"
        per = {"hour": "/h", "year": "/rok"}.get(self.salary_period, "/mies.")
        return f"{f}–{t} {self.currency}{per} {self.contract}".strip()

    def salary_to_pln_month(self, fx: dict) -> float | None:
        if self.salary_to is None:
            return None
        v = self.salary_to * fx.get(self.currency.upper(), 1)
        return {"hour": v * 168, "year": v / 12}.get(self.salary_period, v)
