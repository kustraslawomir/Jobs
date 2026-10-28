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
    assert a1 == "={Oferty!A1:R1}"
    assert a2 == ('=IFERROR(SORT(FILTER(Oferty!A2:R;Oferty!E2:E<>"";Oferty!E2:E<>"Do wysłania";'
                  'Oferty!E2:E<>"Rezygnacja");6;FALSE);"Jeszcze nic nie wysłane")')


def test_mirror_formulas_use_commas_for_en_us():
    assert sheets.arg_separator("en_US") == "," and ";" not in sheets.mirror_formulas(",")[1]


def test_filter_views_cover_whole_columns_and_skip_existing_ones():
    reqs = sheets.filter_view_requests(7, [])
    f = {r["addFilterView"]["filter"]["title"]: r["addFilterView"]["filter"] for r in reqs}
    assert set(f) == {"Do przejrzenia", "Najnowsze", "AI", "Część etatu / zlecenia"}
    todo = f["Do przejrzenia"]
    assert todo["range"] == {"sheetId": 7, "startColumnIndex": 0, "endColumnIndex": 20}       # A:T, bez ograniczenia wierszy
    assert todo["sortSpecs"] == [{"dimensionIndex": sheets.COL["Match"], "sortOrder": "DESCENDING"}]
    assert todo["criteria"] == {"4": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Do wysłania"}]}},
                                "10": {"hiddenValues": ["Senior+"]}}                           # Poziom = kolumna K
    assert f["Najnowsze"]["sortSpecs"] == [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]
    ai = f["AI"]                                                      # AI = kolumna L (11), Status = E (4), Match = J (9)
    assert ai["criteria"] == {"11": {"condition": {"type": "NOT_BLANK"}},
                              "4": {"hiddenValues": ["Przyjęta", "Odrzucone", "Rezygnacja", "Ghosting"]}}
    assert ai["sortSpecs"] == [{"dimensionIndex": 9, "sortOrder": "DESCENDING"}]
    part = f["Część etatu / zlecenia"]                                # Wymiar = kolumna N (13)
    assert part["criteria"] == {"13": {"condition": {"type": "NOT_BLANK"}, "hiddenValues": ["Pełny etat"]}}
    assert part["sortSpecs"] == [{"dimensionIndex": 9, "sortOrder": "DESCENDING"}]
    assert [r["addFilterView"]["filter"]["title"] for r in sheets.filter_view_requests(7, ["Najnowsze"])] == \
        ["Do przejrzenia", "AI", "Część etatu / zlecenia"]
    assert sheets.filter_view_requests(7, ["Najnowsze", "Do przejrzenia", "AI", "Część etatu / zlecenia"]) == []


def test_blank_sheet_detection():
    assert sheets.is_blank([]) and sheets.is_blank([["", ""], [" "]])
    assert not sheets.is_blank([["", ""], ["", "x"]])


NEW = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
       "Match", "Poziom", "AI", "Widełki / forma", "Wymiar", "Kontakt", "Luki", "Dopisz do CV", "Notatki", "Źródło", "Klucz"]
NO_LEVEL = [h for h in NEW if h not in ("Poziom", "AI", "Wymiar")]   # układ sprzed Poziomu, AI i Wymiaru (17 kolumn)
NO_AI = [h for h in NEW if h not in ("AI", "Wymiar")]                # z Poziomem, bez AI i Wymiaru (18 kolumn)
NO_WYMIAR = [h for h in NEW if h != "Wymiar"]                        # z Poziomem i AI, bez Wymiaru (19 kolumn)
OLD = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
       "Alert", "Match", "Luki", "Dopisz do CV", "Kontakt", "Widełki / forma", "Notatki", "Źródło", "Klucz"]


def apply(headers, reqs):
    """Symulacja semantyki API: deleteDimension usuwa kolumnę, insertDimension wstawia pustą (nagłówki "Poziom" i "AI"
    dopisuje potem migrate, w tej samej kolejności), moveDimension wstawia kolumnę PRZED destinationIndex układu wyjściowego."""
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
    names = iter(n for n in ("Poziom", "AI", "Wymiar") if n not in h)
    return [next(names) if c == "" else c for c in h]


def insert(i):
    return {"insertDimension": {"range": {"sheetId": 5, "dimension": "COLUMNS", "startIndex": i, "endIndex": i + 1},
                                "inheritFromBefore": False}}


def test_new_layout_has_20_columns_with_workload_after_pay_and_key_last():
    assert sheets.HEADERS == NEW and len(NEW) == 20
    assert (sheets.COL["Match"], sheets.COL["Poziom"], sheets.COL["AI"], sheets.COL["Widełki / forma"], sheets.COL["Wymiar"],
            sheets.COL["Kontakt"], sheets.COL["Notatki"], sheets.COL["Klucz"]) == (9, 10, 11, 12, 13, 14, 17, 19)
    assert sheets.MIRROR_COLS == 18 and sheets.MIRROR_LAST == "R"
    assert "Alert" not in sheets.COL


def test_migration_of_17_column_layout_inserts_three_columns_without_touching_data():
    reqs = sheets.migration_requests(NO_LEVEL, 5)
    assert reqs == [insert(10), insert(11), insert(13)]
    assert apply(NO_LEVEL, reqs) == NEW


def test_migration_of_older_layouts_inserts_only_missing_columns():
    assert sheets.migration_requests(NO_AI, 5) == [insert(11), insert(13)] and apply(NO_AI, sheets.migration_requests(NO_AI, 5)) == NEW
    assert sheets.migration_requests(NO_WYMIAR, 5) == [insert(13)] and apply(NO_WYMIAR, [insert(13)]) == NEW


def test_migration_of_old_layout_deletes_alert_inserts_columns_and_moves_two():
    reqs = sheets.migration_requests(OLD, 5)
    assert [list(r)[0] for r in reqs] == ["deleteDimension", "insertDimension", "insertDimension", "moveDimension",
                                          "moveDimension", "insertDimension"]
    assert reqs[0]["deleteDimension"]["range"] == {"sheetId": 5, "dimension": "COLUMNS", "startIndex": 9, "endIndex": 10}
    assert apply(OLD, reqs) == NEW


def test_migration_is_idempotent_and_finishes_intermediate_layouts():
    assert sheets.migration_requests(NEW, 5) == []
    no_alert = [h for h in OLD if h != "Alert"]
    reqs = sheets.migration_requests(no_alert, 5)
    assert [list(r)[0] for r in reqs] == ["insertDimension", "insertDimension", "moveDimension", "moveDimension", "insertDimension"]
    assert apply(no_alert, reqs) == NEW
    half = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
            "Match", "Widełki / forma", "Luki", "Dopisz do CV", "Kontakt", "Notatki", "Źródło", "Klucz"]
    reqs = sheets.migration_requests(half, 5)
    assert [list(r)[0] for r in reqs] == ["insertDimension", "insertDimension", "moveDimension", "insertDimension"]
    assert apply(half, reqs) == NEW


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
    o = SimpleNamespace(match=0.83, company="Acme", title="Android Developer", url="https://x", gaps=["Java"],
                        add_to_cv=["Compose"], note="uwaga", level="Senior+", ai="workflow (llm)", workload="Część etatu (1/2)", source="justjoinit", key="justjoinit:1",
                        salary_text=lambda: "B2B 20 000–25 000")
    row = sheets.offer_row(o, "2026-10-27")
    assert len(row) == 20
    assert row[9] == 0.83 and row[10] == "Senior+" and row[11] == "workflow (llm)" and row[12] == "B2B 20 000–25 000"
    assert row[13] == "Część etatu (1/2)" and row[14] == "" and row[15] == "Java" and row[16] == "Compose" and row[17] == "uwaga"
    assert row[18] == "justjoinit" and row[19] == "justjoinit:1"
    assert row[4] == "Do wysłania" and row[0] == "2026-10-27"


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
        r = [""] * 20
        r[1], r[2], r[10], r[17], r[19] = firma, tytul, poziom, notatki, klucz
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
        r = [""] * 20
        r[1], r[2], r[11], r[19] = "Firma", tytul, ai, klucz
        return r
    rows = [row("Android Developer", "", "x:1"), row("Android Developer", "ręcznie", "x:2"),
            row("Android Developer", "", "x:3"), row("Android Developer", "", "x:4")]
    desc = {"x:1": "we build llm powered features, agentic workflows", "x:2": "llm", "x:3": "kotlin compose"}
    assert sheets.ai_backfill(rows, desc, CFG_AI) == [(2, "produkt + workflow (llm, agentic)")]


def test_format_rules_are_added_in_priority_order_and_only_once():
    reqs = sheets.format_requests(7, [])
    rules = [r["addConditionalFormatRule"] for r in reqs]
    assert [r["index"] for r in rules] == [0, 1, 2]                    # szarość (zamknięte) > pomarańcz Senior+ > fiolet AI
    gray, orange, purple = (r["rule"] for r in rules)
    assert gray["booleanRule"]["condition"]["values"][0]["userEnteredValue"] == \
        '=OR($E2="Przyjęta",$E2="Odrzucone",$E2="Rezygnacja",$E2="Ghosting")'
    pl = sheets.format_requests(7, [], ";")[0]["addConditionalFormatRule"]["rule"]["booleanRule"]["condition"]["values"][0]
    assert pl["userEnteredValue"] == '=OR($E2="Przyjęta";$E2="Odrzucone";$E2="Rezygnacja";$E2="Ghosting")'   # locale pl
    assert orange["ranges"] == [{"sheetId": 7, "startRowIndex": 1, "startColumnIndex": 10, "endColumnIndex": 11}]
    assert orange["booleanRule"]["condition"] == {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Senior+"}]}
    assert purple["ranges"] == [{"sheetId": 7, "startRowIndex": 1, "startColumnIndex": 0, "endColumnIndex": 20}]
    assert purple["booleanRule"]["condition"] == {"type": "CUSTOM_FORMULA", "values": [{"userEnteredValue": '=$L2<>""'}]}
    assert sheets.format_requests(7, [gray, orange, purple]) == []


def test_existing_gray_rule_is_kept_on_top_and_ai_rule_goes_below_it():
    mine = {"ranges": [], "booleanRule": {"condition": {"type": "CUSTOM_FORMULA",
                                                        "values": [{"userEnteredValue": '=$E2="Odrzucone"'}]}, "format": {}}}
    reqs = sheets.format_requests(7, [mine])
    assert [r["addConditionalFormatRule"]["index"] for r in reqs] == [1, 2]     # po istniejącej regule, nie przed nią


def test_workload_backfill_fills_blank_cells_only_and_leaves_notes_alone():
    def row(wymiar, klucz):
        r = [""] * 20
        r[2], r[13], r[19] = "Android Developer", wymiar, klucz
        return r
    rows = [row("", "x:1"), row("Zlecenie / kontrakt", "x:2"), row("", "x:3"), row("", "x:4"), row("", "x:5")]
    desc = {"x:1": "praca na 1/2 etatu", "x:2": "pełny etat", "x:3": "Pełny etat, B2B", "x:4": "kotlin compose"}
    assert sheets.workload_backfill(rows, desc) == [(2, "Część etatu (1/2)"), (4, "Pełny etat")]
