"""Proces rekrutacji z treści ogłoszenia: kolumny Etapy (liczba) i Proces rekrutacji (lista etapów).

Szukamy tylko tam, gdzie ogłoszenie samo opisuje proces (fraza w rodzaju "proces rekrutacji", "recruitment process"), i bierzemy
okno tekstu tuż za nią. Liczba etapów: wyraźnie podana ("3 etapy", "trzyetapowy") albo, gdy nie ma jej w tekście, liczba
rozpoznanych różnych etapów, ale dopiero od trzech. Inaczej Etapy zostają puste (brak pewności); samą listę etapów wpisujemy
zawsze, gdy cokolwiek rozpoznano. Zgody RODO ("zgoda na przetwarzanie danych w procesie rekrutacji") nie są opisem procesu."""
import re

import level

WINDOW = 500                    # znaków tekstu znormalizowanego za frazą otwierającą opis procesu
MIN_LISTED = 3                  # tyle rozpoznanych etapów bez podanej liczby wystarcza, by wpisać Etapy (dwa mogą być jedną rozmową)
MAX_STAGES = 8                  # wyraźna liczba spoza 1..MAX_STAGES to raczej coś innego niż etapy

_MARKER = re.compile(
    r"proces\w* rekrutacj\w*|proces\w* rekrutacyjn\w*|etap\w* rekrutacj\w*|etap\w* proces\w*|przebieg\w* rekrutacj\w*|"
    r"przebieg\w* proces\w*|jak wyglada\w* (?:nasz\w* |u nas )?(?:proces|rekrutacj)\w*|rekrutacj\w* (?:przebiega|sklada sie|wyglada|obejmuje)|"
    r"proces\w* selekcji|kroki rekrutacj\w*|recruitment process|recruitment stages|hiring process|interview process|"
    r"selection process|interview (?:stages|steps|rounds)|hiring (?:stages|steps)|how we hire|what to expect|our process|"
    r"the process (?:looks|consists)|process (?:looks like|consists)")
_CONSENT = re.compile(r"zgod\w*|przetwarzan\w*|rodo|gdpr|dane osobow\w*|data processing|consent|personal data|klauzul\w*")
_STAGES = [                                    # (etykieta, wzorzec); kolejność wynika z miejsca w tekście, nie z tej listy
    ("HR", r"rozmow\w* (?:z |wstepn\w* z )?(?:hr|rekruter\w*|recruiter)|(?:hr|recruiter|recruitment) (?:call|interview|screen\w*)|"
           r"\bhr\b|screening|phone screen|intro(?:ductory)? call|rozmow\w* wstepn\w*|wstepn\w* rozmow\w*|rozmow\w* telefoniczn\w*"),
    ("techniczna", r"rozmow\w* technicz\w*|technical (?:interview|call|round|screen\w*|conversation|chat)|tech (?:interview|call|round|screen\w*)|"
                   r"spotkanie technicz\w*|weryfikacja technicz\w*|technical verification|technical discussion"),
    ("live coding", r"live[ -]?coding|pair[ -]?programming|programowanie w parach|coding interview|coding session|sesja kodowania"),
    ("zadanie domowe", r"zadanie domow\w*|zadanie rekrutacyjn\w*|zadanie programistyczn\w*|take[ -]?home|home (?:assignment|task|test)|"
                       r"coding (?:task|challenge|assignment)|zadanie praktyczn\w*|code (?:challenge|test)|test technicz\w*"),
    ("system design", r"system design|projektowanie system\w*|architecture (?:interview|discussion|round)|rozmow\w* o architekturze"),
    ("zespół", r"rozmow\w* z zespolem|spotkanie z zespolem|team (?:interview|meeting|call|fit|round)|meet(?:ing)? (?:the|with the) team|"
               r"culture fit|rozmow\w* kulturow\w*|cultural (?:fit|interview)|spotkanie z (?:przyszlym |przyszlymi )?(?:zespol|wspolpracownik)\w*"),
    ("manager", r"rozmow\w* z (?:cto|ceo|coo|vp|dyrektor\w*|kierownik\w*|manager\w*|menedzer\w*|szef\w*|zalozyciel\w*|founder\w*|"
                r"przelozon\w*|head of \w+)|(?:manager|managerial|hiring manager|cto|ceo|founder) (?:interview|call|round|meeting)|"
                r"final (?:interview|round|call)|rozmow\w* koncow\w*|rozmow\w* finaln\w*"),
]
_STAGE_RES = [(label, re.compile(p)) for label, p in _STAGES]
_NUM_WORDS = {"jeden": 1, "jedna": 1, "dwa": 2, "dwie": 2, "trzy": 3, "cztery": 4, "piec": 5, "sesc": 6, "szesc": 6,
              "one": 1, "two": 2, "three": 3, "four": 4, "five": 5, "six": 6}
_NUM = r"(\d|jeden|jedna|dwa|dwie|trzy|cztery|piec|szesc|one|two|three|four|five|six)"
_COUNT = re.compile(rf"(?<![\d/]){_NUM} (?:krotk\w* |short |technical |techniczn\w* |rekrutacyjn\w* |online )?"
                    r"(?:etap\w*|stage\w*|step\w*|round\w*|krok\w*|spotkan\w*|rozmow\w*|interview\w*)")
_COUNT_ADJ = re.compile(r"\b(dwu|trzy|cztero|pieciu|jedno)etapow\w*")
_ADJ_NUM = {"dwu": 2, "trzy": 3, "cztero": 4, "pieciu": 5, "jedno": 1}


def _number(window: str) -> int | None:
    found = []
    for m in _COUNT.finditer(window):
        v = m.group(1)
        n = int(v) if v.isdigit() else _NUM_WORDS.get(v)
        if n:
            found.append(n)
    for m in _COUNT_ADJ.finditer(window):
        found.append(_ADJ_NUM[m.group(1)])
    found = [n for n in found if 1 <= n <= MAX_STAGES]
    return max(found) if found else None            # max: wyliczanka "1. rozmowa z HR, 2. ..." też wygląda jak liczba


def _stages(window: str) -> list[str]:
    hits = []
    for label, rx in _STAGE_RES:
        m = rx.search(window)
        if m:
            hits.append((m.start(), label))
    return [label for _, label in sorted(hits)]


def assess(text: str) -> tuple[int | None, list[str]]:
    """(liczba etapów albo None gdy brak pewności, lista etapów w kolejności z tekstu). (None, []) = ogłoszenie nie opisuje procesu."""
    t = level.normalize(text)
    for m in _MARKER.finditer(t):
        if _CONSENT.search(t[max(0, m.start() - 100):m.start()]):
            continue                                            # "zgoda na przetwarzanie danych w procesie rekrutacji" itp.
        window = t[m.start():m.start() + WINDOW]
        stages, number = _stages(window), _number(t[max(0, m.start() - 25):m.start() + WINDOW])   # liczba bywa przed frazą: "trzyetapowy proces"
        if not stages and number is None:
            continue
        if number is None and len(stages) >= MIN_LISTED:
            number = len(stages)
        return number, stages
    return None, []


def process_text(stages: list[str]) -> str:
    return ", ".join(stages)
