import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import seen  # noqa: E402
from seen import History, Seen  # noqa: E402


def off(source="justjoinit", sid="1", published="", renewed=""):
    return SimpleNamespace(key=f"{source}:{sid}", source=source, published=published, renewed=renewed)


def summary(h, canonical, no=("linkedin", "ręcznie")):
    return h.summaries(no)[canonical]


def test_iso_date_from_every_portal_format():
    assert seen.iso_date(1792578260314) == "2026-10-21"                       # NFJ, epoch ms
    assert seen.iso_date(1790588036) == "2026-09-28"                          # czyjesteldorado, epoch s
    assert seen.iso_date("2026-10-28T06:40:11.0653213Z") == "2026-10-28"      # JJIT
    assert seen.iso_date("2026-10-27T17:54:37.5597446+01:00") == "2026-10-27"  # SOLID.Jobs
    assert seen.iso_date("2026-10-17") == "2026-10-17" and seen.iso_date("28.10.2026") == "2026-10-28"
    assert seen.iso_date(None) == seen.iso_date("") == seen.iso_date("wczoraj") == ""


def test_refresh_does_not_reset_the_age():
    h = History()
    h.record(off(published="2026-09-01"), "justjoinit:1", "2026-09-05")
    h.record(off(published="2026-10-20"), "justjoinit:1", "2026-10-21")        # portal podbił datę ("bump")
    r = h.by_key["justjoinit:1"]
    assert (r.published, r.latest, r.refreshes, r.first_seen, r.last_seen) == ("2026-09-01", "2026-10-20", 1, "2026-09-05", "2026-10-21")
    s = summary(h, "justjoinit:1")
    assert s.earliest == "2026-09-01" and s.refreshes == 1
    h.record(off(published="2026-10-20"), "justjoinit:1", "2026-10-22")        # ta sama data = brak nowego odświeżenia
    assert h.by_key["justjoinit:1"].refreshes == 1


def test_first_sight_with_a_renewal_date_counts_as_one_refresh_and_old_rows_get_their_dates():
    h = History([Seen("nofluffjobs:9", "nofluffjobs", "nofluffjobs:9", first_seen="2026-10-27", last_seen="2026-10-27")])
    h.record(off("nofluffjobs", "9", published="2026-10-21", renewed="2026-10-27"), "nofluffjobs:9", "2026-10-28")
    r = h.by_key["nofluffjobs:9"]
    assert (r.published, r.latest, r.refreshes) == ("2026-10-21", "2026-10-27", 1)
    assert summary(h, "nofluffjobs:9").earliest == "2026-10-21"                # starsza data publikacji niż pierwszy_raz


def test_duplicate_from_another_portal_with_an_older_date_lowers_the_group_date():
    h = History()
    h.record(off("justjoinit", "1", published="2026-10-10"), "justjoinit:1", "2026-10-27")
    assert summary(h, "justjoinit:1").earliest == "2026-10-10"
    h.record(off("solidjobs", "77", published="2026-08-15"), "justjoinit:1", "2026-10-28")    # duplikat przypisany do oferty kanonicznej
    s = summary(h, "justjoinit:1")
    assert s.earliest == "2026-08-15" and s.portals == 2
    assert [r.earliest() for r in h.groups()["justjoinit:1"]] == ["2026-10-10", "2026-08-15"]


def test_age_falls_back_to_first_seen_when_the_portal_gives_no_date():
    h = History()
    h.record(off("bulldogjob", "5"), "bulldogjob:5", "2026-10-28")
    assert summary(h, "bulldogjob:5").earliest == "2026-10-28"


def test_failed_or_not_run_source_never_marks_an_offer_as_gone():
    h = History()
    h.record(off("justjoinit", "1"), "justjoinit:1", "2026-10-01")
    h.record(off("czyjesteldorado", "2"), "czyjesteldorado:2", "2026-10-01")
    for _ in range(10):                                  # 10 runów, w których źródło zawiodło (albo runner lokalny był offline)
        h.mark_runs({})                                  # żadne źródło nie zwróciło udanego runu
    assert not summary(h, "justjoinit:1").disappeared and h.by_key["justjoinit:1"].missed == 0
    for _ in range(10):                                  # chmura OK, lokalnego runnera nadal brak
        h.mark_runs({"justjoinit": {"justjoinit:other"}})
    assert summary(h, "justjoinit:1").disappeared
    assert not summary(h, "czyjesteldorado:2").disappeared and h.by_key["czyjesteldorado:2"].missed == 0


def test_three_successful_runs_without_the_offer_mark_it_gone_and_reappearing_resets():
    h = History()
    h.record(off("justjoinit", "1"), "justjoinit:1", "2026-10-01")
    for n in (1, 2):
        h.mark_runs({"justjoinit": {"justjoinit:x"}})
        assert not summary(h, "justjoinit:1").disappeared, n
    h.mark_runs({"justjoinit": {"justjoinit:x"}})
    assert summary(h, "justjoinit:1").disappeared
    h.record(off("justjoinit", "1"), "justjoinit:1", "2026-10-10")                # wróciła
    assert not summary(h, "justjoinit:1").disappeared and h.by_key["justjoinit:1"].missed == 0


def test_group_is_gone_only_when_every_counting_source_lost_it():
    h = History()
    h.record(off("justjoinit", "1"), "justjoinit:1", "2026-10-01")
    h.record(off("solidjobs", "2"), "justjoinit:1", "2026-10-01")
    for _ in range(3):
        h.mark_runs({"justjoinit": set(), "solidjobs": {"solidjobs:2"}})          # jeden portal nadal ją ma
    assert not summary(h, "justjoinit:1").disappeared
    for _ in range(3):
        h.mark_runs({"solidjobs": set()})
    assert summary(h, "justjoinit:1").disappeared


def test_windowed_and_manual_sources_cannot_make_an_offer_disappear():
    h = History()
    h.record(off("linkedin", "9"), "linkedin:9", "2026-10-01")
    for _ in range(5):
        h.mark_runs({"linkedin": set()})
    assert not summary(h, "linkedin:9").disappeared


def test_tokens_and_active_value():
    s = seen.Summary("2026-08-01", 1, 2, False)
    assert seen.tokens(s) == [] and seen.tokens(seen.Summary("", 2, 3, False)) == ["Odświeżana 2×", "Wisi na 3 portalach"]
    assert seen.active_value(s, "", "2026-10-28") == "Tak"
    gone = seen.Summary("", 0, 1, True)
    assert seen.active_value(gone, "Tak", "2026-10-28") == "Zniknęła 2026-10-28"
    assert seen.active_value(gone, "Zniknęła 2026-10-20", "2026-10-28") == "Zniknęła 2026-10-20"


def test_notes_are_appended_without_overwriting_and_tokens_are_replaced():
    assert seen.merge_note("Poziom: tytuł senior", ["Odświeżana 2×"]) == "Poziom: tytuł senior. Odświeżana 2×"
    assert seen.merge_note("Agencja. Odświeżana 2×. Wisi na 3 portalach. Poziom: x", ["Odświeżana 3×"]) == "Agencja. Poziom: x. Odświeżana 3×"
    assert seen.merge_note("Odświeżana 2×", []) == ""
    assert seen.merge_note("Agencja? Ustal klienta.. Poziom: a, b", []) == "Agencja? Ustal klienta.. Poziom: a, b"


def test_history_row_roundtrip_and_serial_for_the_age_formula():
    r = Seen("a:1", "a", "a:1", "2026-08-01", "2026-10-27", "2026-10-28", 2, "2026-10-20", 1)
    row = r.to_row()
    assert row[-1] == (seen.dt.date(2026, 8, 1) - seen.dt.date(1899, 12, 30)).days
    assert Seen.from_row([str(x) for x in row]) == r
    assert Seen.from_row(["", "a", ""]) is None
