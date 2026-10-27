import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import passes_filters  # noqa: E402
from sources.solidjobs import relevant, to_offer  # noqa: E402

FIX = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures", "solidjobs_offers.json")
JOBS = json.load(open(FIX, encoding="utf-8"))["jobs"]
F = {"title_require_any": ["android", "kotlin"], "title_mobile_words": ["mobile"], "title_dev_words": ["developer"],
     "title_exclude": [], "remote_only": False, "contract_allow": ["B2B", "UoP", "UZ", "UoD"]}


def test_prefilter_keeps_only_android_kotlin_mobile():
    assert [relevant(j) for j in JOBS] == [True, True, False, False]     # staż z DataScience i frontend React odpadają


def test_android_offer_with_monthly_b2b_salary_and_full_description():
    o = to_offer(JOBS[0])
    assert o.title == "Senior Android Developer (Aosp)" and o.remote is True and o.contract == ["B2B"]
    assert o.salary_text() == "B2B 26 900–30 200"
    assert o.url.startswith("https://solid.jobs/o/") and len(o.description) > 200 and "<" not in o.description


def test_second_form_comes_from_secondary_salary():
    o = to_offer(JOBS[1])
    assert o.contract == ["B2B", "UoP"]
    assert o.salary_text() == "B2B 23 500–27 700 | UoP 17 000–20 000"


def test_internship_is_rejected_by_contract_filter():
    item = dict(JOBS[2], title="Android Developer Internship")
    o = to_offer(item)
    assert o.contract == ["Staż"] and passes_filters(o, F, {"PLN": 1}) == "forma współpracy"
