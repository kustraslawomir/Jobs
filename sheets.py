"""Google Sheets: odczyt słownika i istniejących ofert, dopisywanie nowych."""
import csv
import re
import json
import os
import gspread

import ai_flag
import employment
import level
import seen

HEADERS = ["Dodano", "Firma", "Stanowisko", "Link", "Wiek (dni)", "Aktywna", "Status", "Wysłano CV", "Rozmowa",
           "Następny krok", "Termin", "Match", "Poziom", "AI", "Widełki / forma", "Wymiar", "Kontakt", "Luki", "Dopisz do CV",
           "Notatki", "Źródło", "Klucz"]
COL = {h: i for i, h in enumerate(HEADERS)}           # 0-based
STATUSES = ["Do wysłania", "Wysłane", "Odpowiedź", "Rozmowa", "Zadanie domowe", "Oferta",
            "Przyjęta", "Odrzucone", "Rezygnacja", "Ghosting"]
MIRROR_TAB = "Aplikowane"
def col_letter(i: int) -> str:
    """Litera kolumny dla indeksu 0-based (0 -> A)."""
    out, i = "", i + 1
    while i:
        i, r = divmod(i - 1, 26)
        out = chr(65 + r) + out
    return out


SEEN_TAB = "_widziane"
MIRROR_COLS = COL["Notatki"] + 1   # A:P z Ofert (do Notatek, bez Źródło i Klucz)
MIRROR_LAST = col_letter(MIRROR_COLS - 1)
SOURCE_HEADERS = ["Źródło", "Data", "Pobrane", "Nowe", "Błąd"]
SKILL_HEADERS = ["Kategoria", "Keyword", "Wariant 2", "Wariant 3", "Wariant 4", "Mam?", "Waga 1-3", "Komentarz"]


def connect():
    creds = json.loads(os.environ["GOOGLE_SA_JSON"])
    gc = gspread.service_account_from_dict(creds)
    return gc.open_by_key(os.environ["SHEET_ID"])


def mirror_formulas(sep: str) -> tuple[str, str]:
    """Formuły lustra Ofert: bez wierszy "Do wysłania", "Rezygnacja" i pustych, najpierw ostatnio wysłane (kolumna "Wysłano CV").
    `sep` to separator argumentów: ";" dla arkuszy z polskim (i innym europejskim) locale, "," dla en_US."""
    a1 = f"={{Oferty!A1:{MIRROR_LAST}1}}"          # goła referencja pokazałaby tylko A1; literał tablicowy rozlewa się na MIRROR_COLS kolumn
    st = col_letter(COL["Status"])
    a2 = ('=IFERROR(SORT(FILTER(Oferty!A2:{c}{s}Oferty!{st}2:{st}<>""{s}Oferty!{st}2:{st}<>"Do wysłania"{s}'
          'Oferty!{st}2:{st}<>"Rezygnacja"){s}{sort}{s}FALSE){s}"Jeszcze nic nie wysłane")').format(
        s=sep, c=MIRROR_LAST, st=st, sort=COL["Wysłano CV"] + 1)
    return a1, a2


def sheet_locale(sh) -> str:
    return sh.fetch_sheet_metadata(params={"fields": "properties.locale"})["properties"]["locale"]


def is_blank(values) -> bool:
    return not any(str(c).strip() for row in values for c in row)


def drop_empty_default_sheets(sh):
    """Usuwa domyślną pustą zakładkę ("Arkusz1" / "Sheet1"); jeśli zawiera cokolwiek, zostaje."""
    for ws in sh.worksheets():
        if ws.title in ("Arkusz1", "Sheet1") and len(sh.worksheets()) > 1:
            if is_blank(ws.get_all_values()):
                sh.del_worksheet(ws)
                print(f"Usunięto pustą zakładkę {ws.title!r}.")
            else:
                print(f"Zakładka {ws.title!r} ma dane, zostaje.")


def arg_separator(locale: str) -> str:
    return ";" if (locale or "").lower().startswith("pl") else ","


def header_request(sheet_id: int) -> dict:
    return {"repeatCell": {"range": {"sheetId": sheet_id, "startRowIndex": 0, "endRowIndex": 1},
                           "cell": {"userEnteredFormat": {"textFormat": {"bold": True, "foregroundColor": {"red": 1, "green": 1, "blue": 1}},
                                                          "backgroundColor": {"red": 0.12, "green": 0.31, "blue": 0.47}, "wrapStrategy": "WRAP"}},
                           "fields": "userEnteredFormat(textFormat,backgroundColor,wrapStrategy)"}}


FRESH_DAYS = 30                                   # widok "Świeże": oferty nie starsze niż tyle dni
CLOSED_STATUSES = ["Przyjęta", "Odrzucone", "Rezygnacja", "Ghosting"]      # proces zakończony
FULL_TIME = employment.FULL
FILTER_VIEW_TITLES = ("Do przejrzenia", "Najnowsze", "AI", "Część etatu / zlecenia", "Świeże")


def filter_view_requests(sheet_id: int, existing_titles) -> list[dict]:
    """Widoki filtrów na całych kolumnach zakładki Oferty; pomija te, które już istnieją (po nazwie).
    "Do przejrzenia" pokazuje tylko "Do wysłania" i chowa Poziom "Senior+"."""
    rng = {"sheetId": sheet_id, "startColumnIndex": 0, "endColumnIndex": len(HEADERS)}
    views = [
        ("Do przejrzenia", {"sortSpecs": [{"dimensionIndex": COL["Match"], "sortOrder": "DESCENDING"}],
                            "criteria": {str(COL["Status"]): {"condition": {"type": "TEXT_EQ",
                                                                            "values": [{"userEnteredValue": "Do wysłania"}]}},
                                         str(COL["Poziom"]): {"hiddenValues": [level.SENIOR_PLUS]}}}),
        ("Najnowsze", {"sortSpecs": [{"dimensionIndex": COL["Dodano"], "sortOrder": "DESCENDING"}]}),
        ("AI", {"sortSpecs": [{"dimensionIndex": COL["Match"], "sortOrder": "DESCENDING"}],
                "criteria": {str(COL["AI"]): {"condition": {"type": "NOT_BLANK"}},
                             str(COL["Status"]): {"hiddenValues": CLOSED_STATUSES}}}),
        ("Świeże", {"sortSpecs": [{"dimensionIndex": COL["Match"], "sortOrder": "DESCENDING"}],
                    "criteria": {str(COL["Aktywna"]): {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Tak"}]}},
                                 str(COL["Wiek (dni)"]): {"condition": {"type": "NUMBER_LESS_THAN_EQ",
                                                                        "values": [{"userEnteredValue": str(FRESH_DAYS)}]}},
                                 str(COL["Status"]): {"condition": {"type": "TEXT_EQ",
                                                                    "values": [{"userEnteredValue": "Do wysłania"}]}}}}),
        ("Część etatu / zlecenia", {"sortSpecs": [{"dimensionIndex": COL["Match"], "sortOrder": "DESCENDING"}],
                                    "criteria": {str(COL["Wymiar"]): {"condition": {"type": "NOT_BLANK"},
                                                                      "hiddenValues": [FULL_TIME]}}}),
    ]
    return [{"addFilterView": {"filter": {"title": title, "range": rng, **spec}}}
            for title, spec in views if title not in set(existing_titles)]


def mirror_format_requests(sid: int, offers_index: int | None = None) -> list[dict]:
    """Formatowanie lustra: nagłówek jak w Ofertach, zamrożony 1 wiersz i 2 kolumny, F jako data, Match jako procent."""
    props = {"sheetId": sid, "gridProperties": {"frozenRowCount": 1, "frozenColumnCount": 2}}
    fields = "gridProperties.frozenRowCount,gridProperties.frozenColumnCount"
    if offers_index is not None:
        props["index"] = offers_index + 1               # zaraz po Ofertach
        fields = "index," + fields
    return [
        {"updateSheetProperties": {"properties": props, "fields": fields}},
        header_request(sid),
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Wysłano CV"], "endColumnIndex": COL["Wysłano CV"] + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Match"], "endColumnIndex": COL["Match"] + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "PERCENT", "pattern": "0%"}}},
                        "fields": "userEnteredFormat.numberFormat"}},
    ]


def write_mirror_formulas(ws, sep: str):
    a1, a2 = mirror_formulas(sep)
    ws.update(range_name="A1", values=[[a1]], value_input_option="USER_ENTERED")
    ws.update(range_name="A2", values=[[a2]], value_input_option="USER_ENTERED")


def sync_mirror_formulas(ws, sep: str):
    """Lustro jest tylko do odczytu, więc jego formuły wolno poprawić, gdy odbiegają od wzorca."""
    current = [r[0] if r else "" for r in ws.get("A1:A2", value_render_option="FORMULA")]
    if current != list(mirror_formulas(sep)):
        write_mirror_formulas(ws, sep)
        print("Aplikowane: formuły A1:A2 zaktualizowane.")


def ensure_mirror_tab(sh, offers_ws, locale: str):
    """Zakładka "Aplikowane": tylko do odczytu lustro Ofert. Tworzona raz; istniejącej nie ruszamy."""
    if MIRROR_TAB in [w.title for w in sh.worksheets()]:
        sync_mirror_formulas(sh.worksheet(MIRROR_TAB), arg_separator(locale))
        return None
    sep = arg_separator(locale)
    ws = sh.add_worksheet(MIRROR_TAB, 1000, MIRROR_COLS)
    write_mirror_formulas(ws, sep)
    sh.batch_update({"requests": mirror_format_requests(ws.id, offers_ws.index) + [
        {"addProtectedRange": {"protectedRange": {"range": {"sheetId": ws.id}, "warningOnly": True,
                                                  "description": "Lustro – edytuj w zakładce Oferty"}}},
    ]})
    print(f"Aplikowane: utworzona (locale {locale}, separator '{sep}'), A2 = {ws.acell('A2').value!r}")
    return ws


def refresh_mirror(sh, offers_ws, locale: str):
    """Po zmianie układu Ofert: dopasowuje liczbę kolumn lustra do MIRROR_COLS, przepisuje formuły (A:P) i przestawia formaty."""
    ws = ensure_mirror_tab(sh, offers_ws, locale)
    if ws is not None:
        return ws
    ws = sh.worksheet(MIRROR_TAB)
    sh.batch_update({"requests": [                                                # najpierw miejsce na rozlanie tablicy
        {"updateSheetProperties": {"properties": {"sheetId": ws.id, "gridProperties": {"columnCount": MIRROR_COLS}},
                                   "fields": "gridProperties.columnCount"}},
        {"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": 1},          # czyścimy stare formaty liczb
                        "cell": {"userEnteredFormat": {}}, "fields": "userEnteredFormat.numberFormat"}},
    ] + mirror_format_requests(ws.id)})
    write_mirror_formulas(ws, arg_separator(locale))
    return ws


def ensure_filter_views(sh, offers_ws):
    meta = sh.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),filterViews(title))"})
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == offers_ws.id)
    reqs = filter_view_requests(offers_ws.id, [v["title"] for v in sheet.get("filterViews", [])])
    if reqs:
        sh.batch_update({"requests": reqs})
    meta = sh.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),filterViews(title))"})
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == offers_ws.id)
    print("Widoki filtrów w Ofertach:", [v["title"] for v in sheet.get("filterViews", [])])


def _rule_mentions(rules: list[dict], *needles: str) -> bool:
    return any(json.dumps(n, ensure_ascii=False)[1:-1] in json.dumps(r, ensure_ascii=False) for r in rules for n in needles)


def format_requests(sheet_id: int, existing_rules: list[dict], sep: str = ",") -> list[dict]:
    """Formatowanie warunkowe Ofert, dokładane tylko gdy czegoś brakuje (idempotentne). Kolejność reguł = priorytet:
    1) szarość zamkniętych statusów (jeśli w arkuszu nie ma takiej reguły, dodajemy ją na początku),
    2) Poziom "Senior+" na pomarańczowo,
    3) cały wiersz z niepustą kolumną AI na jasnofioletowo (na końcu, więc szarość i pomarańcz mają pierwszeństwo).
    Formuły są w składni locale arkusza, więc `sep` to separator argumentów jak w mirror_formulas."""
    n = len(existing_rules)
    reqs = []

    def add(rule, at_start=False):
        nonlocal n
        reqs.append({"addConditionalFormatRule": {"index": 0 if at_start else n, "rule": rule}})
        n += 1

    width = len(HEADERS)
    if not _rule_mentions(existing_rules, "Odrzucone", "Rezygnacja", "Ghosting"):
        cond = sep.join(f'${col_letter(COL["Status"])}2="{s}"' for s in CLOSED_STATUSES)
        add({"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": width}],
             "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": f"=OR({cond})"}]},
                             "format": {"backgroundColor": {"red": 0.85, "green": 0.85, "blue": 0.85},
                                        "textFormat": {"foregroundColor": {"red": 0.5, "green": 0.5, "blue": 0.5}}}}}, at_start=True)
    col = COL["Poziom"]
    has_level = any(
        (r.get("booleanRule") or {}).get("condition", {}).get("type") == "TEXT_EQ"
        and [v.get("userEnteredValue") for v in r["booleanRule"]["condition"].get("values", [])] == [level.SENIOR_PLUS]
        and any(x.get("startColumnIndex") == col for x in r.get("ranges", []))
        for r in existing_rules)
    if not has_level:
        add({"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": col, "endColumnIndex": col + 1}],
             "booleanRule": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": level.SENIOR_PLUS}]},
                             "format": {"backgroundColor": {"red": 1.0, "green": 0.76, "blue": 0.4}}}})
    ai_formula = f'=${col_letter(COL["AI"])}2<>""'
    if not _rule_mentions(existing_rules, ai_formula):
        add({"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": width}],
             "booleanRule": {"condition": {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": ai_formula}]},
                             "format": {"backgroundColor": {"red": 0.91, "green": 0.87, "blue": 0.98}}}})
    age = COL["Wiek (dni)"]
    for ctype, value, color in (("NUMBER_GREATER", 90, {"red": 0.96, "green": 0.62, "blue": 0.6}),         # > 90 dni: czerwony
                                ("NUMBER_GREATER", 45, {"red": 1.0, "green": 0.76, "blue": 0.4}),         # > 45 dni: pomarańczowy
                                ("NUMBER_LESS_THAN_EQ", 14, {"red": 0.72, "green": 0.88, "blue": 0.72})):  # <= 14 dni: zielony
        if not _has_condition(existing_rules, ctype, str(value), age):
            add({"ranges": [{"sheetId": sheet_id, "startRowIndex": 1, "startColumnIndex": age, "endColumnIndex": age + 1}],
                 "booleanRule": {"condition": {"type": ctype, "values": [{"userEnteredValue": str(value)}]},
                                 "format": {"backgroundColor": color}}})
    return reqs


def _has_condition(rules: list[dict], ctype: str, value: str, col: int) -> bool:
    for r in rules:
        cond = (r.get("booleanRule") or {}).get("condition") or {}
        if (cond.get("type") == ctype and [v.get("userEnteredValue") for v in cond.get("values", [])] == [value]
                and any(x.get("startColumnIndex") == col for x in r.get("ranges", []))):
            return True
    return False


def ensure_formats(sh, offers_ws, sep: str):
    meta = sh.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),conditionalFormats)"})
    sheet = next(s for s in meta["sheets"] if s["properties"]["sheetId"] == offers_ws.id)
    rules = sheet.get("conditionalFormats", [])
    print("Formatowanie warunkowe Ofert, istniejące reguły:",
          [(r.get("booleanRule", {}).get("condition", {}).get("type") or "gradient",
            [v.get("userEnteredValue") for v in r.get("booleanRule", {}).get("condition", {}).get("values", [])]) for r in rules])
    reqs = format_requests(offers_ws.id, rules, sep)
    if reqs:
        sh.batch_update({"requests": reqs})
    print(f"Formatowanie warunkowe Ofert: dodano {len(reqs)} reguł.")


def check_layout(ws):
    """Zatrzymuje zapis, gdy nagłówki Ofert nie pasują do HEADERS (np. przed migracją): dane trafiłyby do złych kolumn."""
    headers = ws.row_values(1)
    if headers and headers != HEADERS:
        raise RuntimeError("Układ kolumn zakładki Oferty jest inny niż oczekiwany (uruchom tryb migrate). "
                           f"Jest: {headers}")


def migration_requests(headers: list[str], sheet_id: int) -> list[dict]:
    """Kroki zmiany układu: usuń Alert, wstaw puste kolumny "Wiek (dni)" i "Aktywna" zaraz za Link, "Poziom" zaraz za Match i "AI" zaraz za Poziomem, "Widełki / forma" zaraz za AI,
    "Kontakt" zaraz za Widełkami i pustą kolumnę "Wymiar" między nimi. Liczy je z aktualnych nagłówków, więc jest idempotentna i dokańcza układ pośredni.
    Zmienia wyłącznie strukturę kolumn (deleteDimension / insertDimension / moveDimension), więc ręcznie wpisane dane zostają. Niezgodny wynik
    (np. obca kolumna) = ValueError, zanim cokolwiek zostanie zmienione."""
    h, reqs = list(headers), []

    def dim(i):
        return {"sheetId": sheet_id, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1}

    if "Alert" in h:
        i = h.index("Alert")
        reqs.append({"deleteDimension": {"range": dim(i)}})
        h.pop(i)

    for name, anchor in (("Wiek (dni)", "Link"), ("Aktywna", "Wiek (dni)"),       # puste kolumny wstawiane w tej kolejności
                         ("Poziom", "Match"), ("AI", "Poziom")):
        if name not in h and anchor in h:
            i = h.index(anchor) + 1
            reqs.append({"insertDimension": {"range": dim(i), "inheritFromBefore": False}})
            h.insert(i, name)

    def place_after(name, anchor):
        if name not in h or anchor not in h:
            return
        i = h.index(name)
        h.pop(i)
        p = h.index(anchor) + 1                     # docelowa pozycja po przeniesieniu
        h.insert(p, name)
        if i != p:                                  # destinationIndex liczony na układzie sprzed przeniesienia
            reqs.append({"moveDimension": {"source": dim(i), "destinationIndex": p if i > p else p + 1}})

    place_after("Widełki / forma", "AI")
    place_after("Kontakt", "Wymiar" if "Wymiar" in h else "Widełki / forma")
    if "Wymiar" not in h and "Widełki / forma" in h:                   # pusta kolumna zaraz za Widełkami, przed Kontaktem
        i = h.index("Widełki / forma") + 1
        reqs.append({"insertDimension": {"range": dim(i), "inheritFromBefore": False}})
        h.insert(i, "Wymiar")
    if h != HEADERS:
        raise ValueError(f"Po migracji nagłówki nie pasują do nowego układu. Są: {headers} -> {h}")
    return reqs


def migrate(sh, cfg, today: str | None = None):
    """Migracja zakładki Oferty do układu HEADERS: kopia zapasowa, zmiana kolumn, odświeżenie widoków i lustra."""
    import datetime as dt
    today = today or dt.date.today().isoformat()
    ws = sh.worksheet(cfg["sheet"]["tab_offers"])
    reqs = migration_requests(ws.row_values(1), ws.id)
    if not reqs:
        print("Migracja: kolumny Ofert są już w nowym układzie, domykam resztę (walidacje, formaty, widoki, lustro, backfill).")
    else:
        titles = {w.title for w in sh.worksheets()}
        name = f"Oferty_backup_{today}"
        n = 2
        while name in titles:
            name = f"Oferty_backup_{today}_{n}"
            n += 1
        ws.duplicate(new_sheet_name=name)
        print(f"Kopia zapasowa: {name}")
        meta = sh.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),filterViews(title,filterViewId))"})
        views = next(x for x in meta["sheets"] if x["properties"]["sheetId"] == ws.id).get("filterViews", [])
        stale = [{"deleteFilterView": {"filterId": v["filterViewId"]}} for v in views if v["title"] in FILTER_VIEW_TITLES]
        cf = sh.fetch_sheet_metadata(params={"fields": "sheets(properties(sheetId),conditionalFormats)"})
        rules = next(x for x in cf["sheets"] if x["properties"]["sheetId"] == ws.id).get("conditionalFormats", [])
        # reguły z formułami odwołują się do liter kolumn, które się przesuwają: kasujemy własne (od końca), init() doda je od nowa
        ours = [i for i, r in enumerate(rules) if any(k in json.dumps(r, ensure_ascii=False) for k in ('Odrzucone', 'CUSTOM_FORMULA', "Senior+", "NUMBER_"))]
        drop = [{"deleteConditionalFormatRule": {"sheetId": ws.id, "index": i}} for i in sorted(ours, reverse=True)]
        sh.batch_update({"requests": stale + drop + reqs})   # widoki mają stare indeksy kolumn: wracają z init()
        row1 = ws.row_values(1)                            # insertDimension wstawia puste kolumny: nagłówki dopisujemy od razu
        for i, name in enumerate(HEADERS):
            if name in ("Wiek (dni)", "Aktywna", "Poziom", "AI", "Wymiar") and name not in row1:
                ws.update_cell(1, i + 1, name)
        print(f"Migracja: {len(reqs)} operacji na kolumnach, usunięto {len(stale)} widoków filtrów.")
    init(sh, cfg)                                       # idempotentne: walidacje, formaty, widoki, lustro (także po przerwanej migracji)
    refresh_mirror(sh, ws, sheet_locale(sh))
    headers = ws.row_values(1)
    if headers != HEADERS:
        raise RuntimeError(f"Nagłówki Ofert po migracji: {headers}")
    seed_history(sh, cfg, ws)
    backfill_columns(sh, cfg, ws, sheet_locale(sh))
    print("Oferty, nagłówki:", headers)
    print("Oferty, 3 pierwsze wiersze:")
    for row in ws.get(f"A2:{gspread.utils.rowcol_to_a1(1, len(HEADERS)).rstrip('0123456789')}4"):
        print("  ", row)
    mirror = sh.worksheet(MIRROR_TAB)
    print("Aplikowane, nagłówki:", mirror.row_values(1))


def level_backfill(rows: list[list[str]], descriptions: dict[str, str], cfg_level: dict) -> list[tuple[int, str, str | None]]:
    """Dla wierszy Ofert (bez nagłówka) z pustym Poziomem: (numer wiersza w arkuszu, poziom, nowe Notatki albo None).
    Poziom z opisu zapisanego w _opisy (po Kluczu) i tytułu; wiersz bez opisu dostaje "?". Powód oceny jest dopisywany
    do istniejących Notatek. Wiersze z już wpisanym Poziomem (także poprawionym ręcznie) zostają nietknięte."""
    out = []
    for n, r in enumerate(rows, start=2):
        r = r + [""] * len(HEADERS)
        if r[COL["Poziom"]].strip() or not (r[COL["Firma"]].strip() or r[COL["Stanowisko"]].strip()):
            continue
        desc = descriptions.get(r[COL["Klucz"]], "")
        if not desc.strip():
            out.append((n, level.UNKNOWN, None))
            continue
        a = level.assess(r[COL["Stanowisko"]], desc, [], cfg_level)
        old = r[COL["Notatki"]].strip()
        note = f"{old}. {a.note}" if old and a.note else (a.note or None)
        out.append((n, a.level, note))
    return out


def ai_backfill(rows: list[list[str]], descriptions: dict[str, str], cfg_ai: dict) -> list[tuple[int, str]]:
    """Dla wierszy Ofert (bez nagłówka) z pustą kolumną AI i opisem w _opisy: (numer wiersza, wartość AI) tylko tam,
    gdzie coś wykryto. Wypełnionych komórek (np. poprawionych ręcznie) nie ruszamy."""
    out = []
    for n, r in enumerate(rows, start=2):
        r = r + [""] * len(HEADERS)
        desc = descriptions.get(r[COL["Klucz"]], "")
        if r[COL["AI"]].strip() or not desc.strip():
            continue
        value = ai_flag.detect(r[COL["Stanowisko"]], desc, cfg_ai)
        if value:
            out.append((n, value))
    return out


def workload_backfill(rows: list[list[str]], descriptions: dict[str, str]) -> list[tuple[int, str]]:
    """Dla wierszy z pustym Wymiarem i opisem w _opisy: (numer wiersza, wartość) tylko tam, gdzie detektor coś znalazł.
    Informacji o wymiarze nie dopisujemy do Notatek."""
    out = []
    for n, r in enumerate(rows, start=2):
        r = r + [""] * len(HEADERS)
        desc = descriptions.get(r[COL["Klucz"]], "")
        if r[COL["Wymiar"]].strip() or not desc.strip():
            continue
        value = employment.value([], r[COL["Stanowisko"]], desc)
        if value:
            out.append((n, value))
    return out


def age_backfill(rows: list[list[str]], sep: str) -> list[tuple[int, str, str | None]]:
    """Dla wierszy Ofert z danymi: (numer wiersza, formuła Wieku albo None, "Tak" albo None) tylko dla pustych komórek."""
    out = []
    for n, r in enumerate(rows, start=2):
        r = r + [""] * len(HEADERS)
        if not (r[COL["Firma"]].strip() or r[COL["Stanowisko"]].strip()) or not r[COL["Klucz"]].strip():
            continue                                  # puste i ręcznie dopisane wiersze bez Klucza nie mają historii
        age = age_formula(n, sep) if not r[COL["Wiek (dni)"]].strip() else None
        active = "Tak" if not r[COL["Aktywna"]].strip() else None
        if age or active:
            out.append((n, age, active))
    return out


def backfill_columns(sh, cfg, ws, locale: str = "en_US"):
    """Uzupełnia puste komórki Poziomu, AI, Wymiaru, Wieku i Aktywnej w istniejących wierszach (osobne zakresy;
    Notatki tylko dla Poziomu)."""
    rows = ws.get_all_values()[1:]
    descriptions = read_descriptions(sh, cfg)
    levels = level_backfill(rows, descriptions, cfg["level"])
    ais = ai_backfill(rows, descriptions, cfg["ai"])
    data = []
    for n, lvl, note in levels:
        data.append({"range": f"{col_letter(COL['Poziom'])}{n}", "values": [[lvl]]})
        if note is not None:
            data.append({"range": f"{col_letter(COL['Notatki'])}{n}", "values": [[note]]})
    for n, value in ais:
        data.append({"range": f"{col_letter(COL['AI'])}{n}", "values": [[value]]})
    workloads = workload_backfill(rows, descriptions)
    for n, value in workloads:
        data.append({"range": f"{col_letter(COL['Wymiar'])}{n}", "values": [[value]]})
    if data:
        ws.batch_update(data, value_input_option="RAW")
    ages = age_backfill(rows, arg_separator(locale))
    formulas = []
    for n, age, active in ages:
        if age:
            formulas.append({"range": f"{col_letter(COL['Wiek (dni)'])}{n}", "values": [[age]]})
        if active:
            formulas.append({"range": f"{col_letter(COL['Aktywna'])}{n}", "values": [[active]]})
    if formulas:
        ws.batch_update(formulas, value_input_option="USER_ENTERED")
    print("Wiek / Aktywna: uzupełniono", len(ages), "wierszy.")
    from collections import Counter
    print("Poziom: uzupełniono", len(levels), "wierszy:", dict(Counter(u[1] for u in levels)))
    print("AI: uzupełniono", len(ais), "wierszy:", dict(Counter(v.split(" (")[0] for _, v in ais)))
    print("Wymiar: uzupełniono", len(workloads), "wierszy:", dict(Counter(v.split(" (")[0] for _, v in workloads)))


def report(sh, cfg):
    """Tylko odczyt: rozkład Poziomów, przykłady Senior+, wszystkie oferty z AI i trafienia samym "ai" (do przeglądu fałszywych alarmów)."""
    from collections import Counter
    ws = sh.worksheet(cfg["sheet"]["tab_offers"])
    rows = [r + [""] * len(HEADERS) for r in ws.get_all_values()[1:]]
    rows = [r for r in rows if r[COL["Firma"]] or r[COL["Stanowisko"]]]
    desc = read_descriptions(sh, cfg)
    print("Nagłówki Ofert:", ws.row_values(1))
    print(f"Wierszy: {len(rows)}; rozkład Poziomów:", dict(Counter(r[COL["Poziom"]] or "(puste)" for r in rows)))
    print("Przykłady Senior+ (do 5):")
    for r in [r for r in rows if r[COL["Poziom"]] == level.SENIOR_PLUS][:5]:
        print(f"  {r[COL['Firma']]} – {r[COL['Stanowisko']]} | {r[COL['Notatki']]}")
    ai_rows = sorted((r for r in rows if r[COL["AI"]].strip()), key=lambda r: -float((r[COL["Match"]] or "0").rstrip("%").replace(",", ".") or 0))
    history = read_seen(sh, cfg)
    summaries = history.summaries(cfg["ghost"]["no_disappearance"])
    today = __import__("datetime").date.today()
    aged = []
    for r in rows:
        s = summaries.get(r[COL["Klucz"]])
        if s and s.earliest and not s.disappeared:
            aged.append(((today - __import__("datetime").date.fromisoformat(s.earliest)).days, s, r))
    aged.sort(key=lambda x: -x[0])
    print("Wiek: najstarsze aktywne oferty (wiek dni | odświeżenia | portale | oferta):")
    for days, s, r in aged[:10]:
        print(f"  {days:>4} | {s.refreshes}× | {s.portals} | {r[COL['Firma']]} – {r[COL['Stanowisko']]}")
    print(f"Aktywnych ofert z wiekiem: {len(aged)}; starszych niż 45 dni: {sum(1 for d, _, _ in aged if d > 45)}; "
          f"starszych niż 90 dni: {sum(1 for d, _, _ in aged if d > 90)}; zniknęło: {sum(1 for s in summaries.values() if s.disappeared)}")
    print(f"Oferty z AI: {len(ai_rows)}")
    for r in ai_rows:
        print(f"  {r[COL['Firma']]} – {r[COL['Stanowisko']]} – {r[COL['Match']] or '–'} – {r[COL['AI']]}")
    bare = [r for r in ai_rows if ai_flag.only_bare_ai(r[COL["AI"]], r[COL["Stanowisko"]], desc.get(r[COL["Klucz"]], ""), cfg["ai"])]
    print(f"Trafienia samym \"ai\": {len(bare)}")
    for r in bare:
        text = " " + level.normalize(f"{r[COL['Stanowisko']]} {desc.get(r[COL['Klucz']], '')}") + " "
        ctx = [text[max(0, m.start() - 45):m.end() + 45].strip() for m in re.finditer(r"(?<![a-z0-9])ais?(?![a-z0-9])", text)][:3]
        print(f"  {r[COL['Firma']]} – {r[COL['Stanowisko']]} – {r[COL['Match']] or '–'}")
        for c in ctx:
            print(f"      …{c}…")


BACKUP_PREFIX = "Oferty_backup_"


def delete_backup(sh, name: str):
    """Usuwa kopię zapasową zrobioną przez migrate. Dotyka wyłącznie zakładek o nazwie Oferty_backup_*."""
    if not name.startswith(BACKUP_PREFIX):
        raise ValueError(f"Odmowa: usuwam tylko zakładki {BACKUP_PREFIX}*, a podano {name!r}")
    ws = sh.worksheet(name)
    sh.del_worksheet(ws)
    print(f"Usunięto zakładkę {name!r}. Zakładki teraz:", [w.title for w in sh.worksheets()])


def init(sh, cfg, skills_csv="skills.csv"):
    """Zakładki, nagłówki, słownik, walidacja statusów, widoki filtrów, lustro. Idempotentne, nie nadpisuje danych.
    Stary układ kolumn Ofert wymaga najpierw migrate()."""
    s = cfg["sheet"]
    titles = [w.title for w in sh.worksheets()]
    ws = sh.worksheet(s["tab_offers"]) if s["tab_offers"] in titles else sh.add_worksheet(s["tab_offers"], 1000, len(HEADERS))
    check_layout(ws)
    if not ws.row_values(1):
        ws.update(range_name="A1", values=[HEADERS])
    locale = sheet_locale(sh)

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
        {"setDataValidation": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Poziom"], "endColumnIndex": COL["Poziom"] + 1},
                               "rule": {"condition": {"type": "ONE_OF_LIST", "values": [{"userEnteredValue": v} for v in level.LEVELS]},
                                        "showCustomUi": True, "strict": True}}},
        {"repeatCell": {"range": {"sheetId": sid, "startRowIndex": 1, "startColumnIndex": COL["Wiek (dni)"], "endColumnIndex": COL["Wiek (dni)"] + 1},
                        "cell": {"userEnteredFormat": {"numberFormat": {"type": "NUMBER", "pattern": "0"}}}, "fields": "userEnteredFormat.numberFormat"}},
        {"updateDimensionProperties": {"range": {"sheetId": sid, "dimension": "COLUMNS", "startIndex": COL["Klucz"], "endIndex": COL["Klucz"] + 1},
                                       "properties": {"hiddenByUser": True}, "fields": "hiddenByUser"}},
    ]})

    ensure_formats(sh, ws, arg_separator(locale))
    ensure_descriptions_tab(sh, cfg)
    ensure_sources_tab(sh, cfg)
    ensure_seen_tab(sh, cfg)
    ensure_filter_views(sh, ws)
    ensure_mirror_tab(sh, ws, locale)

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
    drop_empty_default_sheets(sh)
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


def tail_source_runs(sh, cfg, n: int) -> list[list[str]]:
    return sh.worksheet(cfg["sheet"]["tab_sources"]).get_all_values()[-n:] if n else []


def ensure_seen_tab(sh, cfg):
    """Ukryta zakładka "_widziane" (historia widzianych ofert, seen.py). Idempotentna, nie rusza istniejących danych."""
    name = cfg["sheet"].get("tab_seen", SEEN_TAB)
    try:
        return sh.worksheet(name)
    except gspread.WorksheetNotFound:
        ws = sh.add_worksheet(name, 1000, len(seen.HEADERS))
        ws.update(range_name="A1", values=[seen.HEADERS])
        sh.batch_update({"requests": [
            {"updateSheetProperties": {"properties": {"sheetId": ws.id, "hidden": True, "gridProperties": {"frozenRowCount": 1}},
                                       "fields": "hidden,gridProperties.frozenRowCount"}},
            {"repeatCell": {"range": {"sheetId": ws.id, "startRowIndex": 1, "startColumnIndex": len(seen.HEADERS) - 1,
                                      "endColumnIndex": len(seen.HEADERS)},
                            "cell": {"userEnteredFormat": {"numberFormat": {"type": "DATE", "pattern": "yyyy-mm-dd"}}},
                            "fields": "userEnteredFormat.numberFormat"}}]})
        return ws


def read_seen(sh, cfg) -> "seen.History":
    try:
        rows = sh.worksheet(cfg["sheet"].get("tab_seen", SEEN_TAB)).get_all_values()[1:]
    except gspread.WorksheetNotFound:
        return seen.History()
    return seen.History(r for r in map(seen.Seen.from_row, rows) if r)


def write_seen(sh, cfg, history: "seen.History"):
    """Przepisuje całą historię (workflowy chmurowy i lokalny mają wspólną kolejkę, więc nie ma wyścigów)."""
    ws = ensure_seen_tab(sh, cfg)
    rows = history.rows()
    if ws.row_count < len(rows) + 2:
        ws.resize(rows=len(rows) + 500)
    ws.batch_clear([f"A2:{col_letter(len(seen.HEADERS) - 1)}{max(ws.row_count, 2)}"])
    if rows:
        ws.update(range_name="A2", values=rows, value_input_option="RAW")


def seed_history(sh, cfg, ws):
    """Migracja: dla wierszy Ofert bez historii zakłada wpis (pierwszy_raz = Dodano); daty z portali dojdą w kolejnym runie."""
    history = read_seen(sh, cfg)
    added = 0
    for r in ws.get_all_values()[1:]:
        r = r + [""] * len(HEADERS)
        key = r[COL["Klucz"]].strip()
        if key and key not in history.by_key:
            day = seen.iso_date(r[COL["Dodano"]])
            history.by_key[key] = seen.Seen(key, r[COL["Źródło"]].strip() or key.split(":", 1)[0], key,
                                            first_seen=day, last_seen=day)
            added += 1
    if added or not history.by_key:
        write_seen(sh, cfg, history)
    print(f"Historia (_widziane): dopisano {added} wpisów, razem {len(history.by_key)}.")


def age_formula(row: int, sep: str, seen_tab: str = SEEN_TAB) -> str:
    """Wiek (dni) = dziś minus najwcześniejsza data z grupy (wszystkie wpisy historii o tym kluczu kanonicznym).
    Formuła w wierszu, więc odporna na sortowanie; wiersz bez historii (np. dopisany ręcznie) zostaje pusty."""
    key = f"${col_letter(COL['Klucz'])}{row}"
    keys = f"{seen_tab}!$A:$A"
    earliest = f"{seen_tab}!${col_letter(len(seen.HEADERS) - 1)}:${col_letter(len(seen.HEADERS) - 1)}"
    return (f'=IF(COUNTIF({keys}{sep}{key})=0{sep}""{sep}TODAY()-MINIFS({earliest}{sep}{keys}{sep}{key}))')


def activity_updates(rows: list[list[str]], summaries: dict, today: str) -> list[dict]:
    """Aktualizacje istniejących wierszy po runie: Aktywna ("Tak" / "Zniknęła RRRR-MM-DD") i tokeny w Notatkach
    ("Odświeżana N×", "Wisi na K portalach"). Dotyka tylko komórek, które się zmieniają."""
    data = []
    for n, r in enumerate(rows, start=2):
        r = r + [""] * len(HEADERS)
        s = summaries.get(r[COL["Klucz"]].strip())
        if not s:
            continue
        active = seen.active_value(s, r[COL["Aktywna"]], today)
        if active != r[COL["Aktywna"]]:
            data.append({"range": f"{col_letter(COL['Aktywna'])}{n}", "values": [[active]]})
        note = seen.merge_note(r[COL["Notatki"]], seen.tokens(s))
        if note != r[COL["Notatki"]].strip() and (note or r[COL["Notatki"]].strip()):
            data.append({"range": f"{col_letter(COL['Notatki'])}{n}", "values": [[note]]})
    return data


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
    return existing_from_rows(ws.get_all_values()[1:])


def existing_from_rows(rows):
    out = []
    for r in rows:
        r = r + [""] * len(HEADERS)
        out.append((r[COL["Klucz"]], r[COL["Firma"]], r[COL["Stanowisko"]], r[COL["Widełki / forma"]]))
    return out, len(rows) + 1   # ostatni zajęty wiersz


def sort_by_match(offers):
    """Match malejąco, oferty z pustym matchem na końcu (kolejność wśród równych zachowana)."""
    return sorted(offers, key=lambda o: (o.match is None, -(o.match or 0)))


def offer_row(o, today: str, row_number: int | None = None, sep: str = ",") -> list:
    row = [""] * len(HEADERS)
    row[COL["Dodano"]] = today
    row[COL["Firma"]] = o.company
    row[COL["Stanowisko"]] = o.title
    row[COL["Link"]] = o.url
    row[COL["Wiek (dni)"]] = age_formula(row_number, sep) if row_number else ""
    row[COL["Aktywna"]] = "Tak" if row_number else ""
    row[COL["Status"]] = "Do wysłania"
    row[COL["Match"]] = round(o.match, 2) if o.match is not None else ""
    row[COL["Poziom"]] = getattr(o, "level", "")
    row[COL["AI"]] = getattr(o, "ai", "")
    row[COL["Wymiar"]] = getattr(o, "workload", "")
    row[COL["Widełki / forma"]] = o.salary_text()
    row[COL["Luki"]] = ", ".join(o.gaps)
    row[COL["Dopisz do CV"]] = ", ".join(o.add_to_cv)
    row[COL["Notatki"]] = getattr(o, "note", "")
    row[COL["Źródło"]] = o.source
    row[COL["Klucz"]] = o.key
    return row


def append_offers(ws, offers, today: str, last_row: int, sep: str = ","):
    """Dopisuje nowe oferty (od najwyższego matchu) i zwraca je w kolejności zapisu."""
    if not offers:
        return []
    check_layout(ws)                                  # nigdy nie zapisujemy do arkusza w starym układzie kolumn
    offers = sort_by_match(offers)
    start = last_row + 1
    end = start + len(offers) - 1
    last_col = gspread.utils.rowcol_to_a1(1, len(HEADERS)).rstrip("0123456789")
    ws.update(range_name=f"A{start}:{last_col}{end}", values=[offer_row(o, today, start + i, sep) for i, o in enumerate(offers)],
              value_input_option="USER_ENTERED")
    return offers
