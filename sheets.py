"""Google Sheets: odczyt słownika i istniejących ofert, dopisywanie nowych."""
import csv
import json
import os
import gspread

HEADERS = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa",
           "Następny krok", "Termin", "Alert", "Match", "Luki", "Dopisz do CV",
           "Kontakt", "Widełki / forma", "Notatki", "Źródło", "Klucz"]
COL = {h: i for i, h in enumerate(HEADERS)}           # 0-based
STATUSES = ["Do wysłania", "Wysłane", "Odpowiedź", "Rozmowa", "Zadanie domowe", "Oferta",
            "Przyjęta", "Odrzucone", "Rezygnacja", "Ghosting"]
SOURCE_HEADERS = ["Źródło", "Data", "Pobrane", "Nowe", "Błąd"]
SKILL_HEADERS = ["Kategoria", "Keyword", "Wariant 2", "Wariant 3", "Wariant 4", "Mam?", "Waga 1-3", "Komentarz"]


def alert_formula(followup_days: int, soon_days: int) -> str:
    """Jedna formuła w nagłówku liczy alerty dla całej kolumny (odporna na sortowanie i ręczne wiersze)."""
    g = "IFERROR(INT(G2:G),0)"
    t = "IFERROR(INT(I2:I),0)"
    f = "IFERROR(INT(F2:F),0)"
    closed = '(E2:E="Przyjęta")+(E2:E="Odrzucone")+(E2:E="Rezygnacja")+(E2:E="Ghosting")'
    return (
        '={"Alert";ARRAYFORMULA(IF(B2:B="","",IF(' + closed + '>0,"",'
        f'IF(({g}>0)*({g}=TODAY()),"Rozmowa dziś",'
        f'IF(({g}>TODAY())*({g}-TODAY()<={soon_days}),"Rozmowa wkrótce",'
        f'IF(({t}>0)*({t}<=TODAY()),"Termin!",'
        f'IF((E2:E="Wysłane")*({f}>0)*(TODAY()-{f}>={followup_days}),"Follow-up",'
        'IF(E2:E="Do wysłania","Wyślij CV","")))))))}'
    )


def connect():
    creds = json.loads(os.environ["GOOGLE_SA_JSON"])
    gc = gspread.service_account_from_dict(creds)
    return gc.open_by_key(os.environ["SHEET_ID"])


def init(sh, cfg, skills_csv="skills.csv"):
    """Jednorazowo: zakładki, nagłówki, słownik, walidacja statusów. Nie nadpisuje danych."""
    s = cfg["sheet"]
    titles = [w.title for w in sh.worksheets()]
    ws = sh.worksheet(s["tab_offers"]) if s["tab_offers"] in titles else sh.add_worksheet(s["tab_offers"], 1000, len(HEADERS))
    if not ws.row_values(1):
        ws.update(range_name="A1", values=[HEADERS])
    ws.update(range_name="J1", values=[[alert_formula(s["followup_days"], s["soon_days"])]], value_input_option="USER_ENTERED")

    sid = ws.id
    sh.batch_update({"requests": [
        {"updateSheetProperties": {"properties": {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2}},
                                   "fields": "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 0, "endRowIndex": 1},
                        "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                                                       "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47}, "wrapStrategy": "WRAP"}},
                        "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy)"}},
        {"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Status"], "endColumnIndex": COL["Status"] + 1},
                               "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in STATUSES]},
                                        "showCustomUi": True, "strict": False}}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Match"], "endColumnIndex": COL["Match"] + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}}, "fields": "userEnteredFormat.numberFormat"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": COL["Klucz"], "endIndex": COL["Klucz"] + 1},
                                       "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
    ]})

    ensure_descriptions_tab(sh, cfg)
    ensure_sources_tab(sh, cfg)

    if s["tab_skills"] not in titles:
        sk = sh.add_worksheet(s["tab_skills"], 300, len(SKILL_HEADERS))
        with open(skills_csv, encoding="utf-8") as f:
            rows = list(csv.reader(f))[1:]
        sk.update(range_name="A1", values=[SKILL_HEADERS] + rows)
        sh.batch_update({"requests": [
            {"setDataValidation": {"range": {"sheetId": sk.id, "startRowIndex": 1, "startColumnIndex": 5, "endColumnIndex": 6},
                                   "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in ["Tak", "Częściowo", "Nie", "Do weryfikacji"]]},
                                            "showCustomUi": True}}},
            {"updateSheetProperties": {"properties": {"sheetId": sk.id, "gridProperties": {"frozenRowCount": 1}}, "fields": "gridProperties.frozenRowCount"}},
        ]})
    return ws


def ensure_descriptions_tab(sh, cfg):
    """Ukryta zakładka "_opisy": klucz | znormalizowany opis. Idempotentna, nie rusza istniejących danych."""
    name = cfg["sheet"]["tab_descriptions"]
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(name, 1000, 2)
        ws.update(range_name="A1", values=[["Klucz", "Opis (znormalizowany, max 20 000 znaków)"]])
        sh.batch_update({"requests": [{"updateSheetProperties": {
            "properties": {"sheetId": ws.id, "hidden": True}, "fields": "hidden"}}]})
        return ws


def ensure_sources_tab(sh, cfg):
    """Zakładka "Źródła": po jednym wierszu na źródło na run. Idempotentna, nie rusza istniejących danych."""
    name = cfg["sheet"]["tab_sources"]
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(name, 1000, len(SOURCE_HEADERS))
        ws.update(range_name="A1", values=[SOURCE_HEADERS])
        sh.batch_update({"requests": [
            {"updateSheetProperties": {"properties": {"sheetId": ws.id, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": 0, "endRowIndex": 1},
                            "cell": {"userEnteredFormat": {"textFormat": {"bold": True}}},
                            "fields": "userEnteredFormat.textFormat.bold"}},
        ]})
        return ws


def last_source_runs(sh, cfg) -> dict[str, tuple[int, str]]:
    """Ostatni zapisany run każdego źródła: nazwa -> (pobrane, błąd)."""
    try:
        rows = sh.worksheet(cfg["sheet"]["tab_sources"]).get_all_values()[1:]
    except gspread.WorksheetNotFound:
        return {}
    out = {}
    for r in rows:
        r = r + [""] * len(SOURCE_HEADERS)
        if r[0]:
            out[r[0]] = (int(r[2]) if r[2].isdigit() else 0, r[4])
    return out


def append_source_runs(sh, cfg, runs: list[tuple], failing: set[str]):
    """runs: [(źródło, data, pobrane, nowe, błąd)]; wiersze źródeł z `failing` malujemy na czerwono."""
    if not runs:
        return
    ws = ensure_sources_tab(sh, cfg)
    start = len(ws.get_all_values()) + 1
    ws.append_rows([list(r) for r in runs], value_input_option="RAW")
    reqs = [{"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": start - 1 + i, "endRowIndex": start + i},
                            "cell": {"userEnteredFormat": {"backgroundColor": {"red": 0.96, "green": 0.8, "blue": 0.8}}},
                            "fields": "userEnteredFormat.backgroundColor"}}
            for i, r in enumerate(runs) if r[0] in failing]
    if reqs:
        sh.batch_update({"requests": reqs})


def read_descriptions(sh, cfg) -> dict[str, str]:
    try:
        rows = sh.worksheet(cfg["sheet"]["tab_descriptions"]).get_all_values()[1:]
    except gspread.WorksheetNotFound:
        return {}
    return {r[0]: r[1] for r in rows if len(r) > 1 and r[0]}


def append_descriptions(sh, cfg, items: list[tuple[str, str]]):
    if items:
        ensure_descriptions_tab(sh, cfg).append_rows([list(i) for i in items], value_input_option="RAW")


def read_skills(sh, cfg):
    return sh.worksheet(cfg["sheet"]["tab_skills"]).get_all_values()[1:]


def read_existing(ws):
    rows = ws.get_all_values()[1:]
    out = []
    for r in rows:
        r = r + [""] * len(HEADERS)
        out.append((r[COL["Klucz"]], r[COL["Firma"]], r[COL["Stanowisko"]], r[COL["Widełki / forma"]]))
    return out, len(rows) + 1   # ostatni zajęty wiersz


def append_offers(ws, offers, today: str, last_row: int):
    if not offers:
        return
    rows = []
    for o in offers:
        row = [""] * len(HEADERS)
        row[COL["Dodano"]] = today
        row[COL["Firma"]] = o.company
        row[COL["Stanowisko"]] = o.title
        row[COL["Link"]] = o.url
        row[COL["Status"]] = "Do wysłania"
        row[COL["Match"]] = round(o.match, 2) if o.match is not None else ""
        row[COL["Luki"]] = ", ".join(o.gaps)
        row[COL["Dopisz do CV"]] = ", ".join(o.add_to_cv)
        row[COL["Widełki / forma"]] = o.salary_text()
        row[COL["Notatki"]] = getattr(o, "note", "")
        row[COL["Źródło"]] = o.source
        row[COL["Klucz"]] = o.key
        rows.append(row)
    start = last_row + 1
    # kolumna J zostaje pusta (liczy ją ARRAYFORMULA z nagłówka)
    left = [r[:COL["Alert"]] for r in rows]
    right = [r[COL["Alert"] + 1:] for r in rows]
    end = start + len(rows) - 1
    ws.update(range_name=f"A{start}:I{end}", values=left, value_input_option="USER_ENTERED")
    ws.update(range_name=f"K{start}:R{end}", values=right, value_input_option="USER_ENTERED")
