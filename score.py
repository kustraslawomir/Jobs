"""Score 0.0-10.0 = ocena szansy na zatrudnienie (kolumna Score). Czysta funkcja wiersza arkusza; wagi i progi w config.yaml (sekcja score).

Składniki 0-1 (średnia ważona): match z CV, poziom, trudność (odwrócona), proces rekrutacji (liczba etapów, live coding, zadanie domowe,
system design), wiek oferty, świeżość (odświeżenia, liczba portali), widełki. Potem bonus za postęp procesu i kara za wcześniejsze odmowy tej firmy.
Liczba aplikacji nie wchodzi: żadne źródło jej nie podaje."""
import re

CLOSED = ("Odrzucone", "Rezygnacja", "Ghosting")
WON = ("Oferta", "Przyjęta")
OPEN_STATUSES = ("", "Do wysłania", "Do rozważenia", "Rozważam")      # tylko tu zniknięcie ogłoszenia zeruje szanse
_SALARY = re.compile(r"(\d[\d ]*)\s*[–-]\s*(\d[\d ]*)")


def num(value) -> float | None:
    """Liczba z komórki ("80%", "0,8", "4", ""); procent daje ułamek."""
    s = str(value or "").strip().replace(" ", "").replace(",", ".")
    pct = s.endswith("%")
    try:
        v = float(s.rstrip("%"))
    except ValueError:
        return None
    return v / 100 if pct else v


def salary_to_pln(text: str) -> float | None:
    """Górna granica pierwszych widełek z tekstu "B2B 23 520–30 240 (…/h)"; tylko PLN (waluty obce: None)."""
    if re.search(r"\b(EUR|USD|GBP|CHF)\b", text or ""):
        return None
    m = _SALARY.search((text or "").split("(")[0])
    return float(m.group(2).replace(" ", "")) if m else None


def _table(rules, value, default):
    for limit, fit in rules:
        if value <= limit:
            return fit
    return default


def compute(row: dict, cfg: dict) -> tuple[float | None, list[str]]:
    """row: match (0-1 albo None), level, difficulty, stages, process, age (dni), active, status, notes, salary_text, firm_rejections.
    Zwraca (wynik albo None gdy brak matchu, rozbicie do notatki)."""
    status, c = row.get("status", ""), cfg
    if status in WON:
        return 10.0, [f"status {status}"]
    if status in CLOSED:
        return 0.0, [f"status {status}"]
    if row.get("active") == "Nie" and status in OPEN_STATUSES:
        return 0.0, ["ogłoszenie nieaktywne"]
    match = row.get("match")
    if match is None:
        return None, []
    notes = row.get("notes", "")
    low_data = "Mało danych do ATS" in notes
    if low_data:
        match = match * (1 - c["low_data_pull"]) + 0.5 * c["low_data_pull"]
    unknown = c["unknown_fit"]
    parts: dict[str, tuple[float, str]] = {"match": (match, f"match {match:.0%}" + (" (mało danych)" if low_data else ""))}
    level = row.get("level") or "?"
    parts["level"] = (c["level_fit"].get(level, c["level_fit"]["?"]), f"poziom {level}")
    diff = row.get("difficulty")
    parts["difficulty"] = ((1 - min(max(diff, 0), 10) / 10, f"trudność {diff:g}") if diff is not None else (unknown, "trudność ?"))
    stages = row.get("stages")
    stage_list = [p.strip() for p in (row.get("process") or "").split(",") if p.strip()]
    if stages is not None:
        fit, label = c["stages_fit"][min(int(stages), max(c["stages_fit"]))], f"{int(stages)} etapów"
    else:
        fit, label = unknown, "etapy ?"
    extra = [p for p in stage_list if p in c["process_penalty"]]
    if extra:
        fit = max(0.0, fit - sum(c["process_penalty"][p] for p in extra))
        label += " + " + ", ".join(extra)
    parts["process"] = (fit, label)
    age = row.get("age")
    parts["age"] = (_table(c["age_fit"], age, 0.1), f"wiek {age:g} d") if age is not None else (unknown, "wiek ?")
    refreshes = int(m.group(1)) if (m := re.search(r"Odświeżana (\d+)×", notes)) else 0
    portals = int(m.group(1)) if (m := re.search(r"Wisi na (\d+) portalach", notes)) else 0
    fresh = 1 - max([p for n, p in c["fresh_refresh_penalty"] if refreshes >= n], default=0) - (c["fresh_portals_penalty"] if portals >= 3 else 0)
    parts["fresh"] = (max(0.0, fresh), f"odświeżana {refreshes}×" if refreshes >= 2 else "świeża")
    top = salary_to_pln(row.get("salary_text", ""))
    parts["salary"] = ((c["salary_high_fit"], f"widełki do {top:,.0f}".replace(",", " ")) if top and top >= c["salary_high_pln"] else
                       (1.0 if top else unknown, "widełki ok" if top else "widełki ?"))

    weights = c["weights"]
    total = sum(weights[k] * parts[k][0] for k in weights) / sum(weights.values()) * 10
    why = [f"{label} {'+' if fit >= 0.75 else '−' if fit <= 0.45 else '·'}" for fit, label in (parts[k] for k in weights)]
    bonus = c["status_bonus"].get(status, 0.0)
    if bonus:
        total += bonus
        why.append(f"status {status} +{bonus:g}")
    bad = int(row.get("firm_rejections") or 0)
    if bad:
        pen = min(bad * c["firm_penalty"], c["firm_penalty_cap"])
        total -= pen
        why.append(f"firma: {bad}× odmowa −{pen:g}")
    return round(min(10.0, max(c["floor"], total)), 1), why
