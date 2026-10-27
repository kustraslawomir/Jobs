import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from dedup import (Deduper, SURE_BY_CONTENT, SURE_BY_TITLE, company_forms, jaccard, norm_company,  # noqa: E402
                   norm_description, norm_title, parse_salary_text, same_company, shingles)
from fixtures import (ANDROID_DESC, BACKEND_DESC, BASE_DESC, IOS_DESC, SIMILAR_DESC, offer, words)  # noqa: E402


def dd_with(*offers):
    dd = Deduper([])
    for o in offers:
        dd.add(o)
    return dd


def test_company_normalization():
    assert norm_company("ACME Sp. z o.o.") == norm_company("Acme")
    assert norm_company("EPAM Systems") == norm_company("EPAM")
    assert same_company(company_forms("j-labs"), company_forms("j-labs software specialist"))
    assert same_company(company_forms("Edge One Solutions Sp. z o.o"), company_forms("Edge One"))
    assert not same_company(company_forms("Antal"), company_forms("Spyrosoft"))


def test_title_normalization():
    bag = lambda t: sorted(norm_title(t).split())   # kolejność słów załatwia token_sort_ratio  # noqa: E731
    assert bag("Programista Android") == bag("Android Developer")
    assert bag("Android Engineer") == bag("Android Developer")
    assert bag("Android Developer (Kotlin, Compose)") == bag("Senior Android Developer")


def test_same_description_epam_vs_epam_systems_is_sure_duplicate():
    dd = dd_with(offer("EPAM Systems", "Senior Android Engineer", BASE_DESC))
    v = dd.check(offer("EPAM", "Android Developer", BASE_DESC, source="justjoinit", sid="2"))
    assert v.rejected and v.rejected.reason == SURE_BY_TITLE


def test_same_description_different_companies_is_caught_by_content_only():
    dd = dd_with(offer("Foo Labs", "Android Developer", BASE_DESC))
    v = dd.check(offer("Bar Corp", "Android Developer", BASE_DESC, source="justjoinit", sid="2"))
    assert v.rejected and v.rejected.reason == SURE_BY_CONTENT


def test_agency_with_same_description_gets_note_and_is_kept():
    dd = dd_with(offer("Spyrosoft", "Android Developer", BASE_DESC))
    v = dd.check(offer("Antal", "Android Developer", BASE_DESC, source="justjoinit", sid="2"))
    assert v.rejected is None
    assert [m.kind for m in v.matches] == ["agency"]
    assert v.notes == ["Agencja – prawdopodobnie oferta Spyrosoft"]


def test_same_company_android_vs_ios_with_shared_boilerplate_is_not_duplicate():
    dd = dd_with(offer("Acme", "Backend Engineer", BACKEND_DESC),
                 offer("Acme", "Mobile Developer", ANDROID_DESC, sid="2"))
    v = dd.check(offer("Acme", "Mobile Developer", IOS_DESC, sid="3"))
    assert v.rejected is None


def test_boilerplate_really_is_what_makes_the_difference():
    # bez trzeciej oferty firmy "o nas" nie jest boilerplate'em, więc treść wygląda na zbieżną
    a, b = shingles(norm_description(ANDROID_DESC)), shingles(norm_description(IOS_DESC))
    assert jaccard(a, b) > 0.6


def test_same_company_and_title_but_disjoint_salaries_is_not_duplicate():
    dd = dd_with(offer("Acme", "Android Developer", BASE_DESC, sal=(15000, 18000)))
    v = dd.check(offer("Acme", "Android Developer", BASE_DESC, sid="2", sal=(25000, 30000)))
    assert v.rejected is None and not v.matches
    v = dd.check(offer("Acme", "Android Developer", BASE_DESC, sid="3", sal=(17000, 22000)))
    assert v.rejected is not None


def test_salary_from_sheet_text_is_used():
    dd = Deduper([("nofluffjobs:1", "Acme", "Android Developer", "15 000–18 000 PLN/mies. B2B (90–107/h)")])
    assert dd.check(offer("Acme", "Android Developer", sal=(25000, 30000))).rejected is None
    assert dd.check(offer("Acme", "Android Developer", sal=(16000, 20000))).rejected is not None


def test_programista_vs_developer_with_070_similarity_is_sure_duplicate():
    c = jaccard(shingles(norm_description(BASE_DESC)), shingles(norm_description(SIMILAR_DESC)))
    assert 0.6 <= c < 0.9, c
    dd = dd_with(offer("Acme", "Android Developer", BASE_DESC))
    v = dd.check(offer("Acme", "Programista Android", SIMILAR_DESC, source="justjoinit", sid="2"))
    assert v.rejected and v.rejected.reason == SURE_BY_TITLE


def test_possible_duplicate_by_content_gets_note():
    dd = dd_with(offer("Foo Labs", "Android Developer", BASE_DESC))
    v = dd.check(offer("Bar Corp", "Android Developer", SIMILAR_DESC, source="justjoinit", sid="2"))
    assert v.rejected is None
    assert len(v.matches) == 1 and v.matches[0].kind == "possible"
    assert v.notes[0].startswith("Możliwy duplikat: Foo Labs – Android Developer (nofluffjobs, treść ")


def test_possible_duplicate_by_title_in_same_company():
    dd = dd_with(offer("Acme", "Android Developer"))
    v = dd.check(offer("Acme", "Android Mobile Developer", sid="2"))
    assert v.rejected is None and [m.kind for m in v.matches] == ["possible"]


def test_without_description_same_company_and_title_is_sure_duplicate():
    dd = dd_with(offer("Acme", "Senior Android Developer"))
    assert dd.check(offer("Acme", "Android Developer (Kotlin, Compose)", sid="2")).rejected is not None


def test_different_titles_same_company_are_not_duplicates():
    dd = dd_with(offer("Acme", "Android Developer"))
    for title in ("Mobile Developer (Flutter)", "iOS Developer"):
        v = dd.check(offer("Acme", title, sid="2"))
        assert v.rejected is None and not v.matches, title


def test_same_id_is_known():
    dd = dd_with(offer("Acme", "Android Developer", sid="7"))
    assert dd.has_key(offer("Acme", "whatever", sid="7"))


def test_parse_salary_text():
    assert parse_salary_text("23 520–29 400 PLN/mies. B2B (140–175/h)", {}) == (23520, 29400)
    assert parse_salary_text("B2B 15 000–18 000 | UoP 12 000–16 000", {}) == (12000, 18000)
    assert parse_salary_text("5 000–6 000 EUR/mies. B2B", {"EUR": 4.3}) == (21500, 25800)
    assert parse_salary_text("brak widełek", {}) is None


def test_short_descriptions_are_not_compared():
    assert shingles(norm_description(words("w", 10))) is None
