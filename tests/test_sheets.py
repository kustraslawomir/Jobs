import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sheets  # noqa: E402


def test_new_offers_are_sorted_by_match_descending_with_empty_match_last():
    offers = [SimpleNamespace(match=m, id=i) for i, m in enumerate([0.5, None, 0.9, 0.5, None, 1.0, 0.0])]
    assert [(o.match, o.id) for o in sheets.sort_by_match(offers)] == [
        (1.0, 5), (0.9, 2), (0.5, 0), (0.5, 3), (0.0, 6), (None, 1), (None, 4)]


def test_mirror_formulas_use_semicolons_for_polish_locale():
    a1, a2 = sheets.mirror_formulas(sheets.arg_separator("pl_PL"))
    assert a1 == "={Oferty!A1:T1}"                                   # A:T = Dodano ... Notatki (bez Źródło i Klucz)
    assert a2 == ('=IFERROR(SORT(FILTER(Oferty!A2:T;Oferty!G2:G<>"";Oferty!G2:G<>"Do wysłania";'
                  'Oferty!G2:G<>"Rezygnacja");8;FALSE);"Jeszcze nic nie wysłane")')      # Status = G, sortowanie po H (Wysłano CV)


def test_mirror_formulas_use_commas_for_en_us():
    assert sheets.arg_separator("en_US") == "," and ";" not in sheets.mirror_formulas(",")[1]


def test_filter_views_cover_whole_columns_and_skip_existing_ones():
    C = sheets.COL
    reqs = sheets.filter_view_requests(7, [])
    f = {r["addFilterView"]["filter"]["title"]: r["addFilterView"]["filter"] for r in reqs}
    titles = {"Do przejrzenia", "Najnowsze", "AI", "Część etatu / zlecenia", "Świeże"}
    assert set(f) == titles == set(sheets.FILTER_VIEW_TITLES)
    todo = f["Do przejrzenia"]
    assert todo["range"] == {"sheetId": 7, "startColumnIndex": 0, "endColumnIndex": 22}       # A:V, bez ograniczenia wierszy
    assert todo["sortSpecs"] == [{"dimensionIndex": C["Match"], "sortOrder": "DESCENDING"}]
    assert todo["criteria"] == {str(C["Status"]): {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Do wysłania"}]}},
                                str(C["Poziom"]): {"hiddenValues": ["Senior+"]}}
    assert f["Najnowsze"]["sortSpecs"] == [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]
    assert f["AI"]["criteria"] == {str(C["AI"]): {"condition": {"type": "NOT_BLANK"}},
                                   str(C["Status"]): {"hiddenValues": ["Przyjęta", "Odrzucone", "Rezygnacja", "Ghosting"]}}
    assert f["AI"]["sortSpecs"] == [{"dimensionIndex": C["Match"], "sortOrder": "DESCENDING"}]
    assert f["Część etatu / zlecenia"]["criteria"] == {str(C["Wymiar"]): {"condition": {"type": "NOT_BLANK"},
                                                                          "hiddenValues": ["Pełny etat"]}}
    fresh = f["Świeże"]                                    # Aktywna = Tak, Wiek <= 30, Status = Do wysłania, Match malejąco
    assert fresh["criteria"] == {
        str(C["Aktywna"]): {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Tak"}]}},
        str(C["Wiek (dni)"]): {"condition": {"type": "NUMBER_LESS_THAN_EQ", "values": [{"userEnteredValue": "30"}]}},
        str(C["Status"]): {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Do wysłania"}]}}}
    assert fresh["sortSpecs"] == [{"dimensionIndex": C["Match"], "sortOrder": "DESCENDING"}]
    left = [r["addFilterView"]["filter"]["title"] for r in sheets.filter_view_requests(7, ["Najnowsze"])]
    assert left[0] == "Do przejrzenia" and set(left) == titles - {"Najnowsze"}
    assert sheets.filter_view_requests(7, list(titles)) == []


def test_blank_sheet_detection():
    assert sheets.is_blank([]) and sheets.is_blank([["", ""], [" "]])
    assert not sheets.is_blank([["", ""], ["", "x"]])


NEW = ["Dodano", "Firma", "Stanowisko", "Link", "Wiek (dni)", "Aktywna", "Status", "Wysłano CV", "Rozmowa", "Następny krok",
       "Termin", "Match", "Poziom", "AI", "Widełki / forma", "Wymiar", "Kontakt", "Luki", "Dopisz do CV", "Notatki", "Źródło", "Klucz"]
NO_LEVEL = [h for h in NEW if h not in ("Wiek (dni)", "Aktywna", "Poziom", "AI", "Wymiar")]   # 17 kolumn, sprzed Poziomu
NO_AGE = [h for h in NEW if h not in ("Wiek (dni)", "Aktywna")]                             # z Poziomem, AI i Wymiarem
NO_WYMIAR = [h for h in NEW if h != "Wymiar"]
OLD = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
       "Alert", "Match", "Luki", "Dopisz do CV", "Kontakt", "Widełki / forma", "Notatki", "Źródło", "Klucz"]


def apply(headers, reqs):
    """Symulacja semantyki API: deleteDimension usuwa kolumnę, insertDimension wstawia pustą (nagłówki dopisuje potem migrate, w tej samej kolejności), moveDimension wstawia kolumnę PRZED destinationIndex układu wyjściowego."""
    h = list(headers)
    for r in reqs:
        if "deleteDimension" in r:
            h.pop(r["deleteDimension"]["range"]["startIndex"])
        elif "insertDimension" in r:
            h.insert(r["insertDimension"]["range"]["startIndex"], "")
        else:
            m = r["moveDimension"]
            i, d = m["source"]["startIndex"], m["destinationIndex"]
            col = h.pop(i)
            h.insert(d - 1 if d > i else d, col)
    names = iter(n for n in ("Wiek (dni)", "Aktywna", "Poziom", "AI", "Wymiar") if n not in h)
    return [next(names) if c == "" else c for c in h]


def insert(i):
    return {"insertDimension": {"range": {"sheetId": 5, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                "inheritFromBefore": False}}


def test_new_layout_has_22_columns_with_age_after_link_and_key_last():
    C = sheets.COL
    assert sheets.HEADERS == NEW and len(NEW) == 22
    assert (C["Link"], C["Wiek (dni)"], C["Aktywna"], C["Status"], C["Match"], C["Poziom"], C["AI"], C["Widełki / forma"],
            C["Wymiar"], C["Kontakt"], C["Notatki"], C["Klucz"]) == (3, 4, 5, 6, 11, 12, 13, 14, 15, 16, 19, 21)
    assert sheets.MIRROR_COLS == 20 and sheets.MIRROR_LAST == "T"
    assert "Alert" not in C


def test_migration_of_17_column_layout_inserts_five_columns_without_touching_data():
    reqs = sheets.migration_requests(NO_LEVEL, 5)
    assert [list(r)[0] for r in reqs] == ["insertDimension"] * 5
    assert [r["insertDimension"]["range"]["startIndex"] for r in reqs] == [4, 5, 12, 13, 15]
    assert apply(NO_LEVEL, reqs) == NEW


def test_migration_of_the_previous_layout_inserts_only_age_and_active_after_link():
    reqs = sheets.migration_requests(NO_AGE, 5)
    assert reqs == [insert(4), insert(5)] and apply(NO_AGE, reqs) == NEW
    assert sheets.migration_requests(NO_WYMIAR, 5) == [insert(15)] and apply(NO_WYMIAR, [insert(15)]) == NEW


def test_migration_of_old_layout_deletes_alert_inserts_columns_and_moves_two():
    reqs = sheets.migration_requests(OLD, 5)
    assert [list(r)[0] for r in reqs] == ["deleteDimension"] + ["insertDimension"] * 4 + ["moveDimension"] * 2 + ["insertDimension"]
    assert reqs[0]["deleteDimension"]["range"] == {"sheetId": 5, "dimension": "COLUMNS", "startIndex": 9, "endIndex": 10}
    assert apply(OLD, reqs) == NEW


def test_migration_is_idempotent_and_finishes_intermediate_layouts():
    assert sheets.migration_requests(NEW, 5) == []
    no_alert = [h for h in OLD if h != "Alert"]
    reqs = sheets.migration_requests(no_alert, 5)
    assert [list(r)[0] for r in reqs].count("moveDimension") == 2 and apply(no_alert, reqs) == NEW
    half = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
            "Match", "Widełki / forma", "Luki", "Dopisz do CV", "Kontakt", "Notatki", "Źródło", "Klucz"]
    reqs = sheets.migration_requests(half, 5)
    assert [list(r)[0] for r in reqs].count("moveDimension") == 1 and apply(half, reqs) == NEW


def test_migration_refuses_unknown_layouts_before_changing_anything():
    import pytest
    with pytest.raises(ValueError):
        sheets.migration_requests(OLD + ["Moja kolumna"], 5)


def test_layout_guard_blocks_writes_to_old_sheets():
    import pytest

    class WS:
        def __init__(self, headers):
            self.headers = headers

        def row_values(self, n):
            return self.headers
    sheets.check_layout(WS(NEW))
    sheets.check_layout(WS([]))                      # pusty arkusz: init wpisze nagłówki
    with pytest.raises(RuntimeError):
        sheets.check_layout(WS(OLD))


def test_offer_row_puts_values_in_the_new_columns():
    C = sheets.COL
    o = SimpleNamespace(match=0.83, company="Acme", title="Android Developer", url="https://x", gaps=["Java"],
                        add_to_cv=["Compose"], note="uwaga", level="Senior+", ai="workflow (llm)", workload="Część etatu (1/2)",
                        source="justjoinit", key="justjoinit:1", salary_text=lambda: "B2B 20 000–25 000")
    row = sheets.offer_row(o, "2026-10-27", 12, ";")
    assert len(row) == 22
    assert (row[C["Match"]], row[C["Poziom"]], row[C["AI"]], row[C["Widełki / forma"]], row[C["Wymiar"]]) == (
        0.83, "Senior+", "workflow (llm)", "B2B 20 000–25 000", "Część etatu (1/2)")
    assert (row[C["Kontakt"]], row[C["Luki"]], row[C["Dopisz do CV"]], row[C["Notatki"]]) == ("", "Java", "Compose", "uwaga")
    assert (row[C["Źródło"]], row[C["Klucz"]], row[C["Status"]], row[C["Dodano"]]) == ("justjoinit", "justjoinit:1", "Do wysłania", "2026-10-27")
    assert row[C["Aktywna"]] == "Tak"
    assert row[C["Wiek (dni)"]] == '=IF(COUNTIF(_widziane!$A:$A;$V12)=0;"";TODAY()-MINIFS(_widziane!$J:$J;_widziane!$A:$A;$V12))'


def test_delete_backup_refuses_anything_but_backup_tabs():
    import pytest
    deleted = []

    class SH:
        def worksheet(self, name):
            return name

        def worksheets(self):
            return []

        def del_worksheet(self, ws):
            deleted.append(ws)
    for name in ("Oferty", "Aplikowane", "Źródła", ""):
        with pytest.raises(ValueError):
            sheets.delete_backup(SH(), name)
    assert deleted == []
    sheets.delete_backup(SH(), "Oferty_backup_2026-10-27")
    assert deleted == ["Oferty_backup_2026-10-27"]


CFG_LEVEL = __import__("yaml").safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                           "config.yaml"), encoding="utf-8"))["level"]


def test_level_backfill_fills_only_blank_cells_and_appends_to_notes():
    def row(firma, tytul, poziom, notatki, klucz):
        r = [""] * 22
        r[1], r[2], r[sheets.COL["Poziom"]], r[sheets.COL["Notatki"]], r[sheets.COL["Klucz"]] = firma, tytul, poziom, notatki, klucz
        return r
    rows = [row("A", "Android Developer", "", "ręczna notatka", "x:1"),       # wiersz 2: opis -> Senior+ (8 lat)
            row("B", "Android Developer", "Mid", "moje", "x:2"),              # wiersz 3: ręcznie ustawiony, bez zmian
            row("C", "Senior Android Developer", "", "", "x:3"),              # wiersz 4: brak opisu -> "?" mimo tytułu
            row("", "", "", "", ""),                                          # pusty wiersz pomijamy
            row("D", "Android Developer", "", "", "x:4")]                     # wiersz 6: brak sygnałów -> "?", bez notatki
    desc = {"x:1": "wymagamy min 8 lat doswiadczenia, system design", "x:2": "10 years", "x:4": "kotlin compose"}
    assert sheets.level_backfill(rows, desc, CFG_LEVEL) == [
        (2, "Senior+", "ręczna notatka. Poziom: 8+ lat, system design"), (4, "?", None), (6, "?", None)]


CFG_AI = __import__("yaml").safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                                        "config.yaml"), encoding="utf-8"))["ai"]


def test_ai_backfill_fills_only_blank_cells_with_a_description_and_a_hit():
    def row(tytul, ai, klucz):
        r = [""] * 22
        r[1], r[2], r[sheets.COL["AI"]], r[sheets.COL["Klucz"]] = "Firma", tytul, ai, klucz
        return r
    rows = [row("Android Developer", "", "x:1"), row("Android Developer", "ręcznie", "x:2"),
            row("Android Developer", "", "x:3"), row("Android Developer", "", "x:4")]
    desc = {"x:1": "we build llm powered features, agentic workflows", "x:2": "llm", "x:3": "kotlin compose"}
    assert sheets.ai_backfill(rows, desc, CFG_AI) == [(2, "produkt + workflow (llm, agentic)")]


def test_format_rules_are_added_in_priority_order_and_only_once():
    C = sheets.COL
    reqs = sheets.format_requests(7, [])
    rules = [r["addConditionalFormatRule"] for r in reqs]
    assert [r["index"] for r in rules] == [0, 1, 2, 3, 4, 5]    # szarość > Senior+ > fiolet AI > Wiek: >90, >45, <=14
    gray, orange, purple, red, amber, green = (r["rule"] for r in rules)
    assert gray["booleanRule"]["condition"]["values"][0]["userEnteredValue"] == \
        '=OR($G2="Przyjęta",$G2="Odrzucone",$G2="Rezygnacja",$G2="Ghosting")'
    pl = sheets.format_requests(7, [], ";")[0]["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]["values"][0]
    assert pl["userEnteredValue"] == '=OR($G2="Przyjęta";$G2="Odrzucone";$G2="Rezygnacja";$G2="Ghosting")'   # locale pl
    assert orange["ranges"] == [{"sheetId": 7, "startRowIndex": 1, "startColumnIndex": C["Poziom"], "endColumnIndex": C["Poziom"] + 1}]
    assert orange["booleanRule"]["condition"] == {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Senior+"}]}
    assert purple["ranges"] == [{"sheetId": 7, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 22}]
    assert purple["booleanRule"]["condition"] == {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$N2<>""'}]}
    age = [{"sheetId": 7, "startRowIndex": 1, "startColumnIndex": C["Wiek (dni)"], "endColumnIndex": C["Wiek (dni)"] + 1}]
    assert [(r["ranges"], r["booleanRule"]["condition"]["type"], r["booleanRule"]["condition"]["values"][0]["userEnteredValue"])
            for r in (red, amber, green)] == [(age, "NUMBER_GREATER", "90"), (age, "NUMBER_GREATER", "45"), (age, "NUMBER_LESS_THAN_EQ", "14")]
    assert red["booleanRule"]["format"] != amber["booleanRule"]["format"]
    assert sheets.format_requests(7, [x["addConditionalFormatRule"]["rule"] for x in reqs]) == []


def test_existing_gray_rule_is_kept_on_top_and_other_rules_go_below_it():
    mine = {"ranges": [], "booleanRule": {"condition": {"type": "CUSTOM_FORMULA",
                                                        "values": [{"userEnteredValue": '=$G2="Odrzucone"'}]}, "format": {}}}
    reqs = sheets.format_requests(7, [mine])
    assert [r["addConditionalFormatRule"]["index"] for r in reqs] == [1, 2, 3, 4, 5]     # po istniejącej regule, nie przed nią


def test_workload_backfill_fills_blank_cells_only_and_leaves_notes_alone():
    def row(wymiar, klucz):
        r = [""] * 22
        r[2], r[sheets.COL["Wymiar"]], r[sheets.COL["Klucz"]] = "Android Developer", wymiar, klucz
        return r
    rows = [row("", "x:1"), row("Zlecenie / kontrakt", "x:2"), row("", "x:3"), row("", "x:4"), row("", "x:5")]
    desc = {"x:1": "praca na 1/2 etatu", "x:2": "pełny etat", "x:3": "Pełny etat, B2B", "x:4": "kotlin compose"}
    assert sheets.workload_backfill(rows, desc) == [(2, "Część etatu (1/2)"), (4, "Pełny etat")]


def test_age_backfill_fills_blank_age_formula_and_active_only_for_rows_with_a_key():
    def row(firma, klucz, wiek="", aktywna=""):
        r = [""] * 22
        r[1], r[sheets.COL["Klucz"]], r[sheets.COL["Wiek (dni)"]], r[sheets.COL["Aktywna"]] = firma, klucz, wiek, aktywna
        return r
    rows = [row("A", "x:1"), row("B", "x:2", "5", "Zniknęła 2026-10-01"), row("C", ""), row("", ""), row("D", "x:4", "", "Tak")]
    out = sheets.age_backfill(rows, ";")
    assert [(n, bool(age), act) for n, age, act in out] == [(2, True, "Tak"), (6, True, None)]
    assert out[0][1] == sheets.age_formula(2, ";")


def test_activity_updates_touch_only_changed_cells_and_keep_the_first_disappearance_date():
    from seen import Summary
    def row(klucz, aktywna, notatki):
        r = [""] * 22
        r[1], r[sheets.COL["Klucz"]], r[sheets.COL["Aktywna"]], r[sheets.COL["Notatki"]] = "F", klucz, aktywna, notatki
        return r
    rows = [row("a", "Tak", "Poziom: x"), row("b", "Tak", ""), row("c", "Zniknęła 2026-10-01", ""), row("d", "", "stara. Odświeżana 2×"),
            row("e", "Tak", "")]
    sums = {"a": Summary("2026-10-01", 3, 3, False), "b": Summary("2026-10-01", 0, 1, True), "c": Summary("", 0, 1, True),
            "d": Summary("", 2, 1, False)}
    data = {d["range"]: d["values"][0][0] for d in sheets.activity_updates(rows, sums, "2026-10-28")}
    L, N = sheets.col_letter(sheets.COL["Aktywna"]), sheets.col_letter(sheets.COL["Notatki"])
    assert data == {f"{N}2": "Poziom: x. Odświeżana 3×. Wisi na 3 portalach", f"{L}3": "Zniknęła 2026-10-28", f"{L}5": "Tak"}
