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
    assert a1 == "=Oferty!A1:P1"
    assert a2 == ('=IFERROR(SORT(FILTER(Oferty!A2:P;Oferty!E2:E<>"";Oferty!E2:E<>"Do wysłania";'
                  'Oferty!E2:E<>"Rezygnacja");6;FALSE);"Jeszcze nic nie wysłane")')


def test_mirror_formulas_use_commas_for_en_us():
    assert sheets.arg_separator("en_US") == "," and ";" not in sheets.mirror_formulas(",")[1]


def test_filter_views_cover_whole_columns_and_skip_existing_ones():
    reqs = sheets.filter_view_requests(7, [])
    f = {r["addFilterView"]["filter"]["title"]: r["addFilterView"]["filter"] for r in reqs}
    assert set(f) == {"Do przejrzenia", "Najnowsze"}
    todo = f["Do przejrzenia"]
    assert todo["range"] == {"sheetId": 7, "startColumnIndex": 0, "endColumnIndex": 18}       # A:R, bez ograniczenia wierszy
    assert todo["sortSpecs"] == [{"dimensionIndex": sheets.COL["Match"], "sortOrder": "DESCENDING"}]
    assert todo["criteria"] == {"4": {"condition": {"type": "TEXT_EQ", "values": [{"userEnteredValue": "Do wysłania"}]}}}
    assert f["Najnowsze"]["sortSpecs"] == [{"dimensionIndex": 0, "sortOrder": "DESCENDING"}]
    assert [r["addFilterView"]["filter"]["title"] for r in sheets.filter_view_requests(7, ["Najnowsze"])] == ["Do przejrzenia"]
    assert sheets.filter_view_requests(7, ["Najnowsze", "Do przejrzenia"]) == []


def test_alert_formula_for_polish_locale_uses_semicolons_everywhere():
    f = sheets.alert_formula(7, 2, sheets.arg_separator("pl_PL"))
    assert f.startswith('={"Alert";ARRAYFORMULA(IF(B2:B="";"";IF(')
    assert "," not in f and "§" not in f
    assert 'IFERROR(INT(G2:G);0)' in f and '<=2);"Rozmowa wkrótce"' in f and '>=7);"Follow-up"' in f
    assert f.endswith('IF(E2:E="Do wysłania";"Wyślij CV";"")))))))}')


def test_alert_formula_for_en_us_uses_commas_and_only_the_array_row_separator_is_a_semicolon():
    f = sheets.alert_formula(7, 2, sheets.arg_separator("en_US"))
    assert f.startswith('={"Alert";ARRAYFORMULA(IF(B2:B="","",IF(')
    assert f.count(";") == 1 and "§" not in f
    assert f.endswith('IF(E2:E="Do wysłania","Wyślij CV","")))))))}')


def test_alert_formula_default_separator_is_a_comma():
    assert sheets.alert_formula(7, 2) == sheets.alert_formula(7, 2, ",")


def test_blank_sheet_detection():
    assert sheets.is_blank([]) and sheets.is_blank([["", ""], [" "]])
    assert not sheets.is_blank([["", ""], ["", "x"]])
