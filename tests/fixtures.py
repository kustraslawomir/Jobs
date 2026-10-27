"""Fixture'y do testów dedupu: deterministyczne opisy zbudowane ze sztucznych słów (bez sieci)."""
from models import Offer


def words(tag: str, n: int, start: int = 0) -> str:
    return " ".join(f"{tag}{i}" for i in range(start, start + n))


def offer(company, title, desc="", source="nofluffjobs", sid="1", sal=None):
    lo, hi = sal or (None, None)
    return Offer(source=source, source_id=sid, url="", company=company, title=title, description=desc,
                 currency="PLN", salary_from=lo, salary_to=hi)


# jeden opis i jego wariant o podobieństwie ok. 0.7 (85 wspólnych słów z 100, reszta inna)
BASE_DESC = words("req", 100)
SIMILAR_DESC = words("req", 85) + " " + words("alt", 15)

# boilerplate "o nas" wspólny dla wszystkich ofert firmy + część specyficzna dla roli
ABOUT_US = words("about", 120)
ANDROID_DESC = ABOUT_US + " " + words("android", 30)
IOS_DESC = ABOUT_US + " " + words("ios", 30)
BACKEND_DESC = ABOUT_US + " " + words("backend", 30)
