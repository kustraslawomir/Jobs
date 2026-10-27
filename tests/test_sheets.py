import os
import sys
from types import SimpleNamespace

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import sheets  # noqa: E402


def test_new_offers_are_sorted_by_match_descending_with_empty_match_last():
    offers = [SimpleNamespace(match=m, id=i) for i, m in enumerate([0.5, None, 0.9, 0.5, None, 1.0, 0.0])]
    assert [(o.match, o.id) for o in sheets.sort_by_match(offers)] == [
        (1.0, 5), (0.9, 2), (0.5, 0), (0.5, 3), (0.0, 6), (None, 1), (None, 4)]
