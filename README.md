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
Tworzy zakładki **Oferty** (19 kolumn A–S, lista statusów i poziomów, widoki filtrów, ukryta kolumna Klucz), **Aplikowane** (lustro wysłanych ofert), **Źródła**, ukrytą **_opisy** i **Słownik** (89 skilli). W Słowniku ustaw „Mam?” przy żółtych pozycjach „Do weryfikacji”, bo do tego czasu liczą się jako braki.

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
- **Poziom** (`level.py`, sekcja `level` w `config.yaml`): Mid / Senior / Senior+ / ?. Kolejność sygnałów: pole poziomu z API portalu, tytuł (mid/regular, senior), wymagane lata w opisie (≤ 4 Mid, 5–7 Senior, 8+ Senior+), potem lista sygnałów podbijających Senior do Senior+ (mentoring, architektura, system design, live coding, LeetCode, zadanie domowe, 4+ etapy). Konflikt = wyższy poziom, brak sygnałów = „?”. Powód trafia do Notatek („Poziom: 8+ lat, system design”). Role liderskie (lead, staff, principal, architect, head, manager, director, lider, kierownik) odsiewa filtr tytułów. Kolumnę można poprawić ręcznie (lista rozwijana); widok „Do przejrzenia” chowa Senior+.
- **AI** (`ai_flag.py`, sekcja `ai` w `config.yaml`): kolumna za Poziomem, wartość „produkt”, „workflow” albo „produkt + workflow” z maks. 3 trafionymi słowami, np. „produkt + workflow (llm, copilot)”. Listy słów (regexy na tekście bez ogonków i interpunkcji, całe słowa) edytujesz w configu. Wiersz z AI jest jasnofioletowy (zamknięte statusy zostają szare), a widok filtra „AI” pokazuje tylko oferty z AI i niezamknięte statusy, po Match malejąco.
- **ATS**: słownik czytany z zakładki Słownik, CV z `cv.txt`. Wynik trafia do kolumn Match, Luki i Dopisz do CV.
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
| czyjesteldorado.pl | dane osadzone w HTML (payload RSC na `/search`), JSON-LD oferty | działa **tylko z domowego IP** (z GitHub Actions 403), więc `runner: local` (patrz „Self-hosted runner”); agreguje też oferty innych portali (m.in. theprotocol.it, inhire.io) |
| bulldogjob.pl | `__NEXT_DATA__` na liście po technologii, JSON-LD oferty | działa (mała pula ofert) |
| solid.jobs | oficjalne publiczne REST API (`/public-api/offers/IT`) | działa, pełny opis w liście |
| theprotocol.it | – | **nie podłączone**: Cloudflare (403 „Just a moment…”) także dla sitemap z robots.txt; nie obchodzimy. Część ofert wpada przez czyjesteldorado.pl |
| it.pracuj.pl | – | **nie podłączone**: Cloudflare (403). Brak publicznego API |
| inhire.io | – | **nie podłączone**: SPA, lista ofert idzie przez wewnętrzne API, którego adresu nie da się ustalić z kodu statycznego. Żeby je dodać: trace z DevTools → Network → Fetch/XHR (URL + fragment odpowiedzi). Część ofert wpada przez czyjesteldorado.pl |

Formy współpracy mapuje `contracts.py` na B2B / UoP / UZ / UoD; nieznane wartości zostają surowe i `--dry-run` wypisuje je jako „nieznana forma”.

## Self-hosted runner (Mac) dla źródeł z `runner: local`

Niektóre portale (teraz czyjesteldorado.pl) blokują adresy IP serwerowni GitHuba (403), ale działają z domowego łącza. Takie źródła w `config.yaml` mają `runner: local` i zbiera je `scrape-local.yml` na Twoim Macu. Pozostałe (`runner: cloud`, domyślnie) zbiera `scrape.yml` w chmurze. Dedup działa wobec całego arkusza, więc kolejność i rozłączność runów nie ma znaczenia.

### Instalacja (jednorazowo)
1. Python ≥ 3.10 na Macu (`python3 --version`; jeśli starszy: `brew install python@3.12`). Repo musi być **prywatne** (self-hosted runner na publicznym repo to ryzyko).
2. GitHub → repo → **Settings → Actions → Runners → New self-hosted runner → macOS**. Strona pokaże komendy z aktualną wersją i jednorazowym tokenem; wykonaj je w terminalu (mają postać):
   ```bash
   mkdir ~/actions-runner && cd ~/actions-runner
   curl -o actions-runner-osx-arm64.tar.gz -L <URL ze strony>
   tar xzf ./actions-runner-osx-arm64.tar.gz
   ./config.sh --url https://github.com/kustraslawomir/Jobs --token <TOKEN ze strony>
   ```
   Przy pytaniach zostaw domyślne (grupa, nazwa, etykiety `self-hosted, macOS, ARM64`).
3. PATH dla usługi (launchd nie widzi Homebrew): `echo "/opt/homebrew/bin:/usr/local/bin:/usr/bin:/bin" > ~/actions-runner/.path`
4. Instalacja jako usługa, żeby startowała po zalogowaniu:
   ```bash
   cd ~/actions-runner
   ./svc.sh install && ./svc.sh start
   ```
5. Workflow `scrape-local.yml` jest **wyłączony** do czasu rejestracji runnera (inaczej joby z crona czekałyby w kolejce bez runnera). Po zarejestrowaniu włącz go: `gh workflow enable scrape-local.yml`.
6. Test: **Actions → Zbieranie ofert (lokalny runner) → Run workflow → dry-run**.

### Jak to działa i jak sprawdzić
- Job `scrape-local` czeka w kolejce na runner **do 24 h**; gdy Mac śpi lub jest wyłączony, wystartuje po jego wybudzeniu (po 24 h GitHub go anuluje). Nie ma wtedy wiersza w zakładce „Źródła”, więc brak runu widać tylko po dacie ostatniego wiersza.
- Status usługi: `cd ~/actions-runner && ./svc.sh status`. Status w GitHubie: **Settings → Actions → Runners** (Idle = gotowy, Active = pracuje, Offline = Mac śpi lub usługa stoi) albo `gh api repos/kustraslawomir/Jobs/actions/runners --jq '.runners[] | [.name,.status,.busy] | @tsv'`.
- Logi runów: `gh run list --workflow=scrape-local.yml`.
- Zatrzymanie / odinstalowanie: `./svc.sh stop`, `./svc.sh uninstall`.
- Venv z zależnościami leży w katalogu roboczym runnera (`_work/Jobs/.venv`), nie w systemowym Pythonie.

## Układ kolumn Ofert i migracja

Kolejność kolumn (A–S): Dodano, Firma, Stanowisko, Link, Status, Wysłano CV, Rozmowa, Następny krok, Termin, Match, Poziom, AI, Widełki / forma, Kontakt, Luki, Dopisz do CV, Notatki, Źródło, Klucz (ukryta). Kolumny Alert już nie ma.

Skrypt nie zapisuje do arkusza, którego nagłówki Ofert różnią się od tego układu (zatrzymuje się z błędem), żeby dane nie trafiły do złych kolumn. Stary arkusz przestawia tryb **migrate** (Actions → Run workflow → `migrate`, lokalnie `python main.py --migrate`):
- robi kopię zakładki jako `Oferty_backup_<data>`,
- zmienia tylko strukturę kolumn (usunięcie Alert, wstawienie pustych kolumn Poziom i AI przez insertDimension, przeniesienie Widełek i Kontaktu), nie przepisuje danych, więc ręczne wpisy zostają,
- uzupełnia puste komórki AI (tylko tam, gdzie coś wykryto) oraz Poziomu na podstawie opisów z ukrytej zakładki _opisy (po Kluczu; brak opisu = „?”) i dopisuje powód do Notatek; komórki z już wpisanym Poziomem zostają,
- jest idempotentna: w nowym układzie nic nie robi, w układzie pośrednim kończy brakujące kroki,
- odtwarza widoki filtrów (A:S, w tym „AI”), dodaje listę wartości i pomarańczowe tło dla Senior+ w kolumnie Poziom, fiolet dla wierszy z AI (szarość zamkniętych statusów ma pierwszeństwo; jeśli arkusz nie ma takiej reguły, zostanie dodana), odświeża Aplikowane (A:Q).
Kopię (`Oferty_backup_*`) usuń ręcznie po sprawdzeniu arkusza.
