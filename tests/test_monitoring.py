import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import main  # noqa: E402

CFG = {"notify": {"telegram": False}}


def run(name, fetched=10, error=""):
    return (name, "2026-10-27", fetched, 0, error)


def test_failure_needs_two_runs_in_a_row():
    prev = {"a": (10, ""), "b": (0, ""), "c": (5, "boom"), "d": (7, "")}
    runs = [run("a", 0), run("b", 0), run("c", 0, "403"), run("d", 12), run("e", 0)]
    assert main.alert_sources(CFG, runs, prev) == {"b", "c"}      # "a" pierwszy raz, "e" bez historii


def test_zero_offers_and_error_both_count_as_failure():
    assert main.is_failed(0, "") and main.is_failed(5, "err") and not main.is_failed(5, "")
