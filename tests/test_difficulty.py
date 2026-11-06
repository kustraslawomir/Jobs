import pytest
import yaml

import difficulty

CONFIG = yaml.safe_load(open("config.yaml", encoding="utf-8"))


def score(title, desc, lvl):
    return difficulty.score(title, desc, lvl, CONFIG["level"], CONFIG["difficulty"])


def test_calm_mid_role_is_low():
    assert score("Android Developer", "Build features in Compose.", "Mid") == (2, ["Mid"])


def test_live_coding_and_leetcode_push_difficulty_up():
    value, why = score("Android Developer", "Stage two: live coding and LeetCode style tasks", "Mid")
    assert value == 8 and why == ["Mid", "live coding", "algorytmy / LeetCode"]


@pytest.mark.parametrize("text", ["No live coding, just a conversation", "Rekrutacja bez live codingu"])
def test_negated_signals_do_not_count(text):
    assert score("Android Developer", text, "Mid") == (2, ["Mid"])


def test_pressure_is_capped_and_score_is_clamped_to_ten():
    value, why = score("Android Developer", "fast paced startup, on call duty", "Mid")
    assert value == 4 and why[1:] == ["presja / tempo", "dyżury", "startup / wiele ról"]
    value, _ = score("Tech", "live coding leetcode system design mentoring architecture ownership of the architecture", "Senior+")
    assert value == 10


def test_unknown_level_gets_middle_default_and_no_level_reason():
    assert score("Android Developer", "", "?") == (3, [])
