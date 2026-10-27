import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import level  # noqa: E402
from main import title_reason  # noqa: E402
from models import Offer  # noqa: E402

CONFIG = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                          "config.yaml"), encoding="utf-8"))
CFG = CONFIG["level"]


def lvl(title="Android Developer", desc="", portal=()):
    return level.assess(title, desc, list(portal), CFG)


@pytest.mark.parametrize("text,years", [
    ("5+ years of experience", 5), ("Min. 6 lat doświadczenia", 6), ("at least 7 years", 7),
    ("3-5 years in Android", 3), ("3–5 lat", 3), ("od 4 lat w Androidzie", 4), ("1 year", 1),
    ("2 years Kotlin, 6 years Android", 6), ("minimum 10 yrs", 10),
])
def test_years_required(text, years):
    assert level.years_required(text) == years


@pytest.mark.parametrize("text", [
    "We have 20 years on the market", "firma działa od 15 lat na rynku", "in the last 5 years we grew",
    "ostatnich 3 lat", "founded 12 years ago", "no numbers here", "latest 5 features",
])
def test_years_ignored_when_not_a_requirement(text):
    assert level.years_required(text) is None


def test_years_buckets():
    assert lvl(desc="4 years").level == "Mid"
    assert lvl(desc="5+ years").level == "Senior" and lvl(desc="7 lat").level == "Senior"
    assert lvl(desc="8+ years").level == "Senior+"


@pytest.mark.parametrize("title,expected", [
    ("Mid Android Developer", "Mid"), ("Regular Kotlin Developer", "Mid"), ("Senior Android Engineer", "Senior"),
    ("Android Developer (Mid/Senior)", "Senior"), ("Android Developer", "?"), ("Sr. Android Developer", "Senior"),
])
def test_title(title, expected):
    assert lvl(title).level == expected


@pytest.mark.parametrize("portal,expected", [
    (["mid"], "Mid"), (["Regular"], "Mid"), (["medium"], "Mid"), (["senior"], "Senior"), (["Senior"], "Senior"),
    (["Mid", "Senior"], "Senior"), (["Lead"], "Senior+"), (["Expert"], "Senior+"), (["c_level"], "Senior+"),
    (["junior"], "?"), (["other"], "?"), ([], "?"),
])
def test_portal_field(portal, expected):
    assert lvl(portal=portal).level == expected


def test_conflict_takes_the_higher_level():
    a = lvl("Mid Android Developer", "8+ years of experience")
    assert a.level == "Senior+" and a.reasons == ["tytuł mid", "8+ lat"]
    assert lvl("Senior Android Developer", "2 years", portal=["mid"]).level == "Senior"


def test_signals_bump_senior_to_senior_plus_and_explain_it():
    a = lvl("Senior Android Developer", "You will be doing system design and live-coding in the process")
    assert a.level == "Senior+" and a.reasons == ["tytuł senior", "system design", "live coding"]
    assert a.note == "Poziom: tytuł senior, system design, live coding"
    a = lvl(desc="Wymagamy min. 8 lat doświadczenia. Rozmowa obejmuje System Design.")
    assert a.note == "Poziom: 8+ lat, system design"


def test_signals_do_not_raise_mid_or_unknown():
    assert lvl("Mid Android Developer", "system design, mentoring juniors").level == "Mid"
    a = lvl(desc="system design, take-home assignment")
    assert a.level == "?" and a.note == ""


@pytest.mark.parametrize("text,label", [
    ("You will be mentoring junior developers", "mentoring / prowadzenie zespołu"),
    ("leading the team of 5 engineers", "mentoring / prowadzenie zespołu"),
    ("prowadzenie zespołu programistów", "mentoring / prowadzenie zespołu"),
    ("ownership of architecture of the app", "ownership of architecture"),
    ("Odpowiedzialność za architekturę aplikacji", "ownership of architecture"),
    ("technical leadership of the mobile guild", "technical leadership"),
    ("Przywództwo techniczne", "technical leadership"),
    ("Live-Coding session", "live coding"),
    ("LeetCode style tasks", "algorytmy / LeetCode"),
    ("zadania algorytmiczne", "algorytmy / LeetCode"),
    ("a take-home assignment", "zadanie domowe"),
    ("Zadanie rekrutacyjne", "zadanie domowe"),
    ("4 stages of recruitment", "4+ etapy rekrutacji"),
    ("proces w 5 etapach", "4+ etapy rekrutacji"),
    ("cztery rozmowy", "4+ etapy rekrutacji"),
])
def test_each_bump_signal_is_recognized(text, label):
    assert label in level.bump_signals(text, CFG)


@pytest.mark.parametrize("text", [
    "2 stages of recruitment", "three rounds", "we value team spirit", "mentoring programme for you",
])
def test_bump_signals_do_not_fire_on_ordinary_text(text):
    assert level.bump_signals(text, CFG) == []


def test_assessment_works_on_normalized_stored_descriptions():
    from dedup import norm_description
    stored = norm_description("Wymagamy min. 6 lat doświadczenia. Przywództwo techniczne i Live-coding.")
    assert lvl(desc=stored).level == "Senior+"


def test_offer_accepts_portal_seniority_as_string_or_list():
    kw = dict(source="x", source_id="1", url="", company="A", title="T")
    assert Offer(**kw, seniority="senior").seniority == ["senior"]
    assert Offer(**kw, seniority=["Mid", "Senior"]).seniority == ["Mid", "Senior"]
    assert Offer(**kw, seniority="").seniority == [] and Offer(**kw, seniority=None or []).seniority == []


@pytest.mark.parametrize("title", [
    "Lead Android Developer", "Tech Lead Android", "Team Lead (Android)", "Android Team Leader", "Staff Android Engineer",
    "Principal Mobile Engineer", "Android Architect", "Head of Mobile Development", "Mobile Engineering Manager",
    "Director of Android", "Lider zespołu Android", "Kierownik projektu Android", "Mobile Tech-Lead",
])
def test_leadership_titles_are_filtered_out(title):
    assert title_reason(title, CONFIG["filters"]) is not None


@pytest.mark.parametrize("title", ["Senior Android Developer", "Mid Kotlin Developer", "Android Developer", "Staffing Android Dev"])
def test_regular_titles_still_pass(title):
    assert title_reason(title, CONFIG["filters"]) is None
