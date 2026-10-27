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
    assert a1 == "=Oferty!A1:O1"
    assert a2 == ('=IFERROR(SORT(FILTER(Oferty!A2:O;Oferty!E2:E<>"";Oferty!E2:E<>"Do wysłania";'
                  'Oferty!E2:E<>"Rezygnacja");6;FALSE);"Jeszcze nic nie wysłane")')


def test_mirror_formulas_use_commas_for_en_us():
    assert sheets.arg_separator("en_US") == "," and ";" not in sheets.mirror_formulas(",")[1]


def test_filter_views_cover_whole_columns_and_skip_existing_ones():
    reqs = sheets.filter_view_requests(7, [])
    f = {r["addFilterView"]["filter"]["title"]: r["addFilterView"]["filter"] for r in reqs}
    assert set(f) == {"Do przejrzenia", "Najnowsze"}
    todo = f["Do przejrzenia"]
    assert todo["range"] == {"sheetId": 7, "startColumnIndex": 0, "endColumnIndex": 17}       # A:Q, bez ograniczenia wierszy
    assert todo["sortSpecs"] == [{"dimensionIndex": sheets.COL["Match"], "sortOrder": "DESCENDING"}]
    assert todo["criteria"] == {"4": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Do wysłania"}]}}}
    assert f["Najnowsze"]["sortSpecs"] == [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]
    assert [r["addFilterView"]["filter"]["title"] for r in sheets.filter_view_requests(7, ["Najnowsze"])] == ["Do przejrzenia"]
    assert sheets.filter_view_requests(7, ["Najnowsze", "Do przejrzenia"]) == []


def test_blank_sheet_detection():
    assert sheets.is_blank([]) and sheets.is_blank([["", ""], [" "]])
    assert not sheets.is_blank([["", ""], ["", "x"]])


NEW = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
       "Match", "Widełki / forma", "Kontakt", "Luki", "Dopisz do CV", "Notatki", "Źródło", "Klucz"]
OLD = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
       "Alert", "Match", "Luki", "Dopisz do CV", "Kontakt", "Widełki / forma", "Notatki", "Źródło", "Klucz"]


def apply(headers, reqs):
    """Symulacja semantyki API: deleteDimension usuwa kolumnę, moveDimension wstawia ją PRZED destinationIndex układu wyjściowego."""
    h = list(headers)
    for r in reqs:
        if "deleteDimension" in r:
            h.pop(r["deleteDimension"]["range"]["startIndex"])
        else:
            m = r["moveDimension"]
            i, d = m["source"]["startIndex"], m["destinationIndex"]
            col = h.pop(i)
            h.insert(d - 1 if d > i else d, col)
    return h


def test_new_layout_has_17_columns_with_key_last():
    assert sheets.HEADERS == NEW and len(NEW) == 17
    assert (sheets.COL["Match"], sheets.COL["Widełki / forma"], sheets.COL["Kontakt"], sheets.COL["Klucz"]) == (9, 10, 11, 16)
    assert "Alert" not in sheets.COL


def test_migration_of_old_layout_deletes_alert_and_moves_two_columns():
    reqs = sheets.migration_requests(OLD, 5)
    assert [list(r)[0] for r in reqs] == ["deleteDimension", "moveDimension", "moveDimension"]
    assert reqs[0]["deleteDimension"]["range"] == {"sheetId": 5, "dimension": "COLUMNS", "startIndex": 9, "endIndex": 10}
    assert (reqs[1]["moveDimension"]["source"]["startIndex"], reqs[1]["moveDimension"]["destinationIndex"]) == (13, 10)
    assert (reqs[2]["moveDimension"]["source"]["startIndex"], reqs[2]["moveDimension"]["destinationIndex"]) == (13, 11)
    assert apply(OLD, reqs) == NEW


def test_migration_is_idempotent_and_finishes_intermediate_layouts():
    assert sheets.migration_requests(NEW, 5) == []
    no_alert = [h for h in OLD if h != "Alert"]
    reqs = sheets.migration_requests(no_alert, 5)
    assert [list(r)[0] for r in reqs] == ["moveDimension", "moveDimension"] and apply(no_alert, reqs) == NEW
    half = ["Dodano", "Firma", "Stanowisko", "Link", "Status", "Wysłano CV", "Rozmowa", "Następny krok", "Termin",
            "Match", "Widełki / forma", "Luki", "Dopisz do CV", "Kontakt", "Notatki", "Źródło", "Klucz"]
    reqs = sheets.migration_requests(half, 5)
    assert len(reqs) == 1 and apply(half, reqs) == NEW


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
                        add_to_cv=["Compose"], note="uwaga", source="justjoinit", key="justjoinit:1",
                        salary_text=lambda: "B2B 20 000–25 000")
    row = sheets.offer_row(o, "2026-10-27")
    assert len(row) == 17
    assert row[9] == 0.83 and row[10] == "B2B 20 000–25 000" and row[11] == "" and row[12] == "Java"
    assert row[13] == "Compose" and row[14] == "uwaga" and row[15] == "justjoinit" and row[16] == "justjoinit:1"
    assert row[4] == "Do wysłania" and row[0] == "2026-10-27"
