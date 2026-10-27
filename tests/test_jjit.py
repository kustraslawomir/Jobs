import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.justjoinit import _salary, _job_posting_description  # noqa: E402


def et(unit, frm, to, fpu, tpu):
    return {"from": frm, "to": to, "fromPerUnit": fpu, "toPerUnit": tpu,
            "currency": "PLN", "currencySource": "original", "type": "b2b", "unit": unit}


def test_hourly_rate_in_contract():
    frm, to, cur, period, contract = _salary({"employmentTypes": [et("Hour", 23520, 29400, 140, 175)]})
    assert (frm, to, cur, period, contract) == (23520, 29400, "PLN", "month", "B2B (140–175/h)")


def test_equal_hourly_rate_single_number():
    assert _salary({"employmentTypes": [et("Hour", 22680, 22680, 135, 135)]})[4] == "B2B (135/h)"


def test_month_and_year_have_no_suffix():
    assert _salary({"employmentTypes": [et("Month", 20000, 25000, 20000, 25000)]})[4] == "B2B"
    assert _salary({"employmentTypes": [et("Year", 51841, 55081, 622096, 660977)]})[4] == "B2B"


def test_description_from_json_ld():
    page = ('<html><script type="application/ld+json">{"@type":"JobPosting",'
            '"description":"<p>Kotlin</p><ul><li>Compose</li></ul> &amp; Dagger"}</script></html>')
    assert _job_posting_description(page) == "Kotlin Compose & Dagger"
