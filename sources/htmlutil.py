"""Wspólne narzędzia do źródeł opartych na stronach HTML: JSON-LD JobPosting i czyszczenie tekstu."""
import html
import json
import re

_LD_JSON = re.compile(r'<script[^>]*application/ld\+json[^>]*>(.*?)</script>', re.S | re.I)
_DROP = re.compile(r"<(script|style)\b.*?</\1>", re.S | re.I)
_TAG = re.compile(r"<[^>]+>")


def clean_text(text: str) -> str:
    return re.sub(r"\s+", " ", html.unescape(_TAG.sub(" ", text))).strip()


def page_text(page: str) -> str:
    """Cały widoczny tekst strony (ostateczność, gdy nie ma JSON-LD)."""
    return clean_text(_DROP.sub(" ", page))


def job_posting(page: str) -> dict | None:
    """Pierwszy węzeł JobPosting z JSON-LD (schema.org); stabilniejszy niż klasy CSS czy wewnętrzny stan frameworka."""
    for m in _LD_JSON.finditer(page):
        try:
            data = json.loads(m.group(1))
        except ValueError:
            continue
        nodes = data if isinstance(data, list) else data.get("@graph", [data]) if isinstance(data, dict) else []
        for node in nodes:
            if isinstance(node, dict) and node.get("@type") == "JobPosting":
                return node
    return None


def job_posting_description(page: str) -> str:
    node = job_posting(page)
    return clean_text(str(node["description"])) if node and node.get("description") else ""


def next_flight(page: str) -> str:
    """Złożony payload RSC Next.js (self.__next_f.push([1,"..."])) jako zwykły tekst."""
    chunks = re.findall(r'self\.__next_f\.push\(\[1,"(.*?)"\]\)</script>', page, re.S)
    return "".join(json.loads('"' + c + '"') for c in chunks)


def array_after(text: str, marker: str) -> list:
    """Parsuje tablicę JSON zaczynającą się zaraz po `marker` (marker kończy się na '[')."""
    i = text.find(marker)
    if i < 0:
        return []
    arr, _ = json.JSONDecoder().raw_decode(text[i + len(marker) - 1:])
    return arr
