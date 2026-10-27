# job-scraper

Dwa razy dziennie zbiera oferty Androidowe z JustJoinIT i NoFluffJobs, odsiewa duplikaty, liczy ATS match względem słownika skilli i CV, a nowe oferty dopisuje do Google Sheets. Opcjonalnie wysyła powiadomienie na Telegram.

## Setup (jednorazowo, ~20 min)

### 1. Google Cloud: konto serwisowe
1. https://console.cloud.google.com → nowy projekt (np. `job-tracker`).
2. **APIs & Services → Library** → włącz **Google Sheets API**.
3. **IAM & Admin → Service Accounts → Create** → nazwa dowolna, bez ról.
4. Wejdź w konto → **Keys → Add key → JSON**. Pobierze się plik `.json`. **Nie commituj go.**
5. Skopiuj e-mail konta serwisowego (`...@...iam.gserviceaccount.com`).

### 2. Google Sheet
1. Utwórz pusty arkusz.
2. **Udostępnij** go mailowi konta serwisowego jako **Edytor**.
3. ID arkusza to fragment URL między `/d/` a `/edit`.

### 3. Repo na GitHubie
1. Utwórz **prywatne** repo (CV jest w `cv.txt`), wrzuć te pliki.
2. **Settings → Secrets and variables → Actions → New repository secret**:
   - `GOOGLE_SA_JSON`: cała zawartość pliku `.json` z kroku 1.4
   - `SHEET_ID`: ID arkusza
   - (opcjonalnie) `TELEGRAM_TOKEN`, `TELEGRAM_CHAT_ID`: bot z @BotFather, chat ID np. z @userinfobot

### 4. Przygotowanie arkusza (lokalnie, raz)
```bash
pip install -r requirements.txt
export GOOGLE_SA_JSON="$(cat klucz.json)"
export SHEET_ID=...
python main.py --init
```
Tworzy zakładki **Oferty** (nagłówki, lista statusów, alerty liczone formułą, ukryta kolumna Klucz) i **Słownik** (89 skilli). W Słowniku ustaw „Mam?” przy żółtych pozycjach „Do weryfikacji”, bo do tego czasu liczą się jako braki.

### 5. Sprawdzenie źródeł (WAŻNE)
Portale nie mają oficjalnego API, więc adresy i pola w `sources/*.py` to ich wewnętrzne endpointy strony i **trzeba je zweryfikować**:
1. Wejdź na portal, odfiltruj Androida, otwórz DevTools → Network → Fetch/XHR.
2. Znajdź request zwracający listę ofert i porównaj URL, parametry i nazwy pól z plikiem źródła.
3. Test bez arkusza: `python main.py --dry-run`

Potem: zakładka **Actions → Zbieranie ofert → Run workflow**, żeby odpalić ręcznie i obejrzeć log.

## Jak działa
- **Filtry** w `config.yaml`: słowa w tytule, wykluczenia, tylko remote, minimalne widełki, minimalny match.
- **Deduplikacja**:
  1. to samo ID z portalu (kolumna Klucz),
  2. ta sama firma (po normalizacji: bez „sp. z o.o.”, polskich znaków itd.) i podobny tytuł (fuzzy ≥ 90) z innego portalu,
  3. agencje: tylko notatka „ustal klienta”, decyzja należy do Ciebie.
- **ATS**: słownik czytany z zakładki Słownik, CV z `cv.txt`. Wynik trafia do kolumn Match, Luki i Dopisz do CV.
- **Alerty** liczy formuła w nagłówku kolumny Alert, więc działają też dla wierszy dopisanych ręcznie.
- Wiersze w arkuszu możesz edytować i sortować dowolnie. Skrypt tylko dopisuje na dole i nigdy nie nadpisuje.

## Utrzymanie
- Źródło zwraca 0 ofert albo błąd → endpoint się zmienił, popraw plik w `sources/` (krok 5).
- Nowy portal → nowy plik w `sources/` z funkcją `fetch(session) -> list[Offer]` i wpis w `sources/__init__.py` oraz `config.yaml`.
- Nowe CV → podmień `cv.txt`.
- Nie zwiększaj częstotliwości. 2× dziennie wystarczy, a częściej to prośba o bana.

## Stan źródeł (sprawdzone 2026-10-27)

| Źródło | Metoda | Stan |
|---|---|---|
| justjoin.it | wewnętrzne JSON API (`/api/candidate-api/offers`) + JSON-LD oferty | działa |
| nofluffjobs.com | wewnętrzne JSON API | działa |
| czyjesteldorado.pl | dane osadzone w HTML (payload RSC na `/search`), JSON-LD oferty | działa, agreguje też oferty innych portali (m.in. theprotocol.it, inhire.io) |
| bulldogjob.pl | `__NEXT_DATA__` na liście po technologii, JSON-LD oferty | działa (mała pula ofert) |
| solid.jobs | oficjalne publiczne REST API (`/public-api/offers/IT`) | działa, pełny opis w liście |
| theprotocol.it | – | **nie podłączone**: Cloudflare (403 „Just a moment…”) także dla sitemap z robots.txt; nie obchodzimy. Część ofert wpada przez czyjesteldorado.pl |
| it.pracuj.pl | – | **nie podłączone**: Cloudflare (403). Brak publicznego API |
| inhire.io | – | **nie podłączone**: SPA, lista ofert idzie przez wewnętrzne API, którego adresu nie da się ustalić z kodu statycznego. Żeby je dodać: trace z DevTools → Network → Fetch/XHR (URL + fragment odpowiedzi). Część ofert wpada przez czyjesteldorado.pl |

Formy współpracy mapuje `contracts.py` na B2B / UoP / UZ / UoD; nieznane wartości zostają surowe i `--dry-run` wypisuje je jako „nieznana forma”.
