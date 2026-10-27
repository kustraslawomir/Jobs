import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from sources.justjoinit import _pay, _job_posting_description  # noqa: E402


def et(typ, unit, frm, to, fpu, tpu, cur="PLN", src="original"):
    return {"from": frm, "to": to, "fromPerUnit": fpu, "toPerUnit": tpu, "currency": cur,
            "currencySource": src, "type": typ, "unit": unit}


def test_hourly_rate_kept_only_for_hour_unit():
    contracts, pays = _pay({"employmentTypes": [et("b2b", "Hour", 23520, 29400, 140, 175)]})
    assert contracts == ["B2B"]
    assert (pays[0].lo, pays[0].hi, pays[0].hourly) == (23520, 29400, (140, 175))


def test_month_and_year_have_no_hourly_part():
    for unit, fpu, tpu in (("Month", 20000, 25000), ("Year", 622096, 660977)):
        _, pays = _pay({"employmentTypes": [et("b2b", unit, 20000, 25000, fpu, tpu)]})
        assert pays[0].hourly is None


def test_all_contract_forms_are_listed():
    contracts, pays = _pay({"employmentTypes": [
        et("b2b", "Month", 20000, 25000, 20000, 25000),
        et("permanent", "Month", 15000, 18000, 15000, 18000),
        et("mandate_contract", "Month", None, None, None, None),
        et("b2b", "Month", 4600, 5800, 4600, 5800, cur="EUR", src="conversion")]})
    assert contracts == ["B2B", "UoP", "UZ"]
    assert [(p.contract, p.hi, p.currency) for p in pays] == [("B2B", 25000, "PLN"), ("UoP", 18000, "PLN")]


def test_description_from_json_ld():
    page = ('<html><script type="application/ld+json">{"@type":"JobPosting",'
            '"description":"<p>Kotlin</p><ul><li>Compose</li></ul> &amp; Dagger"}</script></html>')
    assert _job_posting_description(page) == "Kotlin Compose & Dagger"
