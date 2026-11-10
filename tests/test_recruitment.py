import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import recruitment  # noqa: E402


def test_numbered_list_of_stages_gives_count_and_ordered_stages():
    text = "Nasz proces rekrutacji: 1. rozmowa z HR, 2. rozmowa techniczna, 3. live coding, 4. spotkanie z zespołem. Oferujemy..."
    assert recruitment.assess(text) == (4, ["HR", "techniczna", "live coding", "zespół"])


def test_explicit_number_wins_and_english_is_understood():
    assert recruitment.assess("Recruitment process: 3 stages – intro call, take-home task, final interview with CTO") == (
        3, ["HR", "zadanie domowe", "manager"])
    assert recruitment.assess("Trzyetapowy proces rekrutacji: rozmowa z HR i rozmowa techniczna")[0] == 3


def test_three_listed_stages_without_a_number_are_counted():
    assert recruitment.assess("Proces rekrutacji: rozmowa z HR, rozmowa techniczna, zadanie domowe") == (
        3, ["HR", "techniczna", "zadanie domowe"])


def test_uncertain_count_stays_empty_but_stages_are_listed():
    assert recruitment.assess("Proces rekrutacji: rozmowa techniczna z live coding") == (None, ["techniczna", "live coding"])
    assert recruitment.assess("Hiring process: technical interview only") == (None, ["techniczna"])


def test_no_description_of_the_process_means_nothing():
    assert recruitment.assess("Mamy live coding w pracy codziennie. Pair programming. Rozmowa z HR to nie wszystko.") == (None, [])
    assert recruitment.assess("") == (None, [])


def test_gdpr_consent_is_not_a_process_description():
    assert recruitment.assess("Wyrażam zgodę na przetwarzanie danych osobowych w procesie rekrutacji. Zadanie domowe, rozmowa z HR") == (None, [])
