import os
import sys

import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import score  # noqa: E402

CFG = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "config.yaml")))["score"]
GOOD = {"match": 0.9, "level": "Mid", "difficulty": 2, "stages": 2, "process": "HR, techniczna", "age": 3, "status": "Do wysłania",
        "salary_text": "B2B 20 000–26 000", "notes": ""}


def test_good_fresh_easy_offer_scores_high_and_hard_old_one_low():
    hi, _ = score.compute(GOOD, CFG)
    lo, _ = score.compute({**GOOD, "match": 0.45, "level": "Senior+", "difficulty": 9, "stages": 6, "process": "HR, live coding, zadanie domowe",
                           "age": 120, "notes": "Odświeżana 20×"}, CFG)
    assert hi > 8.5 and lo < 3.5 and 1.0 <= lo and hi <= 10.0


def test_age_stages_and_live_coding_each_lower_the_score():
    base, _ = score.compute(GOOD, CFG)
    assert score.compute({**GOOD, "age": 45}, CFG)[0] < base
    assert score.compute({**GOOD, "stages": 5}, CFG)[0] < base
    assert score.compute({**GOOD, "process": "HR, live coding"}, CFG)[0] < base
    assert score.compute({**GOOD, "firm_rejections": 1}, CFG)[0] == round(base - 1.5, 1)


def test_unknowns_are_neutral_not_zero_and_missing_match_leaves_score_empty():
    v, why = score.compute({**GOOD, "stages": None, "process": "", "age": None, "difficulty": None}, CFG)
    assert 5 < v < 9 and "etapy ?" in " ".join(why)
    assert score.compute({**GOOD, "match": None}, CFG) == (None, [])


def test_low_data_pulls_match_toward_neutral():
    assert score.compute({**GOOD, "notes": "Mało danych do ATS – sprawdź opis ręcznie"}, CFG)[0] < score.compute(GOOD, CFG)[0]


def test_closed_inactive_and_won_statuses_are_hard_values():
    assert score.compute({**GOOD, "status": "Ghosting"}, CFG)[0] == 0.0
    assert score.compute({**GOOD, "status": "Odrzucone"}, CFG)[0] == 0.0
    assert score.compute({**GOOD, "active": "Nie"}, CFG)[0] == 0.0
    assert score.compute({**GOOD, "status": "Wysłane", "active": "Nie"}, CFG)[0] > 5          # CV poszło: zniknięcie ogłoszenia nie zeruje
    assert score.compute({**GOOD, "status": "Oferta"}, CFG)[0] == 10.0


def test_progress_bonus_and_cell_parsing():
    assert score.compute({**GOOD, "status": "Rozmowa"}, CFG)[0] > score.compute({**GOOD, "status": "Wysłane"}, CFG)[0]
    assert (score.num("80%"), score.num("0,8"), score.num("4"), score.num("")) == (0.8, 0.8, 4.0, None)
    assert score.salary_to_pln("B2B 23 520–30 240 (140–180/h)") == 30240 and score.salary_to_pln("B2B 5 000–6 000 EUR") is None
