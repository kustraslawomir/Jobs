import os
import sys

import pytest

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from contracts import is_known, normalize  # noqa: E402
from main import passes_filters  # noqa: E402
from models import Offer  # noqa: E402

F = {"title_require_any": ["android"], "title_mobile_words": [], "title_dev_words": [], "title_exclude": [],
     "remote_only": False, "contract_allow": ["B2B", "UoP", "UZ", "UoD"]}


@pytest.mark.parametrize("raw,code", [
    ("b2b", "B2B"), ("B2B", "B2B"),
    ("permanent", "UoP"), ("employment_contract", "UoP"), ("Umowa o pracę", "UoP"), ("uop", "UoP"),
    ("mandate_contract", "UZ"), ("zlecenie", "UZ"), ("Umowa zlecenie", "UZ"),
    ("specific_task_contract", "UoD"), ("uod", "UoD"), ("Umowa o dzieło", "UoD"),
    ("internship", "Staż"), ("staż", "Staż"),
])
def test_mapping(raw, code):
    assert normalize(raw) == code


@pytest.mark.parametrize("raw", ["any", "other", "", None])
def test_unspecified_means_no_information(raw):
    assert normalize(raw) == ""


def test_unknown_value_stays_raw_and_is_not_known():
    assert normalize("freelance") == "freelance" and not is_known("freelance")


def offer(*contract):
    return Offer(source="x", source_id="1", url="", company="Acme", title="Android Developer",
                 contract=list(contract))


@pytest.mark.parametrize("raw", ["b2b", "permanent", "mandate_contract", "specific_task_contract", "zlecenie", "uod"])
def test_each_allowed_form_passes(raw):
    assert passes_filters(offer(raw), F, {}) is None


@pytest.mark.parametrize("raw", ["internship", "staż", "freelance"])
def test_internship_and_unknown_forms_are_rejected(raw):
    assert passes_filters(offer(raw), F, {}) == "forma współpracy"


def test_internship_next_to_allowed_form_still_passes():
    assert passes_filters(offer("internship", "b2b"), F, {}) is None


def test_unspecified_forms_pass():
    assert passes_filters(offer("any"), F, {}) is None and passes_filters(offer(), F, {}) is None
