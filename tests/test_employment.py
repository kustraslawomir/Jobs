import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import employment  # noqa: E402
from main import passes_filters  # noqa: E402
from models import Offer, Pay  # noqa: E402


@pytest.mark.parametrize("text,expected", [
    ("Praca na 1/2 etatu", ["część etatu (1/2)"]),
    ("Zatrudnienie w wymiarze 1/4 etatu", ["część etatu (1/4)"]),
    ("3/4 etatu", ["część etatu (3/4)"]),
    ("pół etatu, zdalnie", ["część etatu"]),
    ("Part-time Android developer", ["część etatu"]),
    ("około 20 godzin tygodniowo", ["część etatu (20 h/tydz.)"]),
    ("pracujemy 8 godzin w tygodniu nad X", ["część etatu (8 h/tydz.)"]),
    ("20 h/tydzień", ["część etatu (20 h/tydz.)"]),
    ("20 hours per week", ["część etatu (20 h/tydz.)"]),
    ("40 hours per week", []),
    ("Umowa zlecenie", ["zlecenie / kontrakt"]),
    ("Freelance project", ["zlecenie / kontrakt"]),
    ("Pełny etat, B2B, Kotlin", []),
    ("Praca na część etatu, zlecenie", ["część etatu", "zlecenie / kontrakt"]),
])
def test_text_signals(text, expected):
    assert employment.labels([], "Android Developer", text) == expected


def test_portal_fields():
    assert employment.labels(["part_time"], "T", "") == ["część etatu"]
    assert employment.labels(["Part-time"], "T", "") == ["część etatu"]
    assert employment.labels(["freelance"], "T", "") == ["zlecenie / kontrakt"]
    assert employment.labels(["Contract"], "T", "") == ["zlecenie / kontrakt"]
    assert employment.labels(["full_time", "b2b_contract"], "T", "") == []


def test_note_text():
    assert employment.note([], "T", "1/2 etatu") == "Wymiar: część etatu (1/2)"
    assert employment.note([], "T", "pełny etat") == ""


F = {"title_require_any": ["android"], "title_mobile_words": [], "title_dev_words": [], "title_exclude": [],
     "remote_only": True, "contract_allow": [], "min_salary_to_pln": 18000}


def off(**kw):
    return Offer(source="x", source_id="1", url="", company="A", title="Android Developer", remote=True,
                 pay=[Pay("B2B", 6000, 9000)], **kw)


def test_reduced_hours_and_gigs_skip_the_minimum_salary_filter():
    fx = {"PLN": 1}
    assert passes_filters(off(), F, fx) == "za niskie widełki"
    assert passes_filters(off(employment=["part_time"]), F, fx) is None
    assert passes_filters(off(description="praca na 1/2 etatu"), F, fx) is None
    assert passes_filters(off(employment="freelance"), F, fx) is None
