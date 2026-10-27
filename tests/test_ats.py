import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import ats  # noqa: E402

SKILLS = ats.load_skills([
    ["", "kotlin", "", "", "", "Tak", "1"],
    ["", "compose", "", "", "", "Tak", "1"],
    ["", "dagger", "", "", "", "Częściowo", "1"],
    ["", "graphql", "", "", "", "Tak", "1"],
])


def test_below_threshold_gives_no_match():
    match, gaps, _, n = ats.evaluate("Kotlin and Compose", SKILLS, "")
    assert n == 2 and match is None and gaps == []


def test_at_threshold_gives_match():
    match, _, _, n = ats.evaluate("Kotlin, Compose, Dagger", SKILLS, "")
    assert n == ats.MIN_REQUIREMENTS == 3
    assert match == (1 + 1 + 0.5) / 3
