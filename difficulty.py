"""Ocena trudności oferty w skali 0-10 (kolumna Trudność): poziom + sygnały trudnej rozmowy / roli + presja w opisie.

Tylko z tekstu ogłoszenia, więc to filtr wstępny: o realnym stresie w firmie nic nie mówi. Wagi w config.yaml (sekcja difficulty)."""
import re

import level


def score(title: str, description: str, level_value: str, cfg_level: dict, cfg: dict) -> tuple[int, list[str]]:
    """Zwraca (trudność 0-10, powody). `level_value` to wynik level.assess ("Mid" | "Senior" | "Senior+" | "?" albo puste)."""
    text = f"{title} {description}"
    points = float(cfg["level_points"].get(level_value or level.UNKNOWN, cfg["level_points"].get(level.UNKNOWN, 3)))
    why = [level_value] if level_value and level_value != level.UNKNOWN else []
    for label in level.negation_safe_signals(text, cfg_level, list(cfg["signal_points"])):
        points += cfg["signal_points"][label]
        why.append(label)
    t = f" {level.normalize(text)} "
    pressure = [label for label, patterns in cfg["pressure"].items() if any(re.search(p, t) for p in patterns)]
    if pressure:
        points += min(len(pressure), cfg["pressure_cap"])
        why += pressure
    return max(0, min(10, int(points + 0.5))), why
