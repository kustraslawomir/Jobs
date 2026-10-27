import os
import sys

import pytest
import yaml

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from main import title_reason  # noqa: E402

F = yaml.safe_load(open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                                     "config.yaml"), encoding="utf-8"))["filters"]


@pytest.mark.parametrize("title", [
    "Mobile Developer", "Senior Android Engineer", "Kotlin Developer",
    "Android Developer (Reactive)", "Android Linux Engineer",
])
def test_passes(title):
    assert title_reason(title, F) is None


@pytest.mark.parametrize("title", [
    "Product Manager – Mobile Apps", "Senior UI/UX Designer", "Senior Test Automation Engineer (Mobile)",
    "Mobile Designer", "Senior Backend Engineer",
])
def test_rejected(title):
    assert title_reason(title, F) is not None
