# Job scraper – skróty komend

Użytkownik pisze krótko. Tłumacz jego komendy tak:

- "odśwież oferty" / "zaktualizuj plik" / "zaktualizuj arkusz" / "pobierz nowe"
  → odpal OBA workflow w trybie run: `gh workflow run scrape.yml -f mode=run` i `gh workflow run scrape-local.yml -f mode=run`, poczekaj (`gh run watch`), pokaż tabelę: źródło | pobrane | nowe | błąd. Jeśli runner lokalny jest offline (`gh api repos/kustraslawomir/Jobs/actions/runners`), odpal tylko chmurowy i powiedz to wprost.
- "test" / "sprawdź" → to samo, ale mode=dry-run (nic nie zapisuje).
- "dodaj ofertę <link lub tekst>" → `gh workflow run scrape.yml -f mode=add -f url=<link>` (albo -f text=...).
- "co jest w arkuszu" → przeczytaj Oferty przez gspread i pokaż top 10 ze statusem "Do wysłania" po matchu.
- "napraw <źródło>" → uruchom dry-run, znajdź błąd źródła w logu, popraw parser, pytest, commit, push, dry-run.

Zasady:
- Arkusz edytujemy tylko przez kod/workflow, nigdy ręcznie przepisując dane.
- Nie usuwaj wierszy z Ofert (dedup na nich stoi).
- Zmiana układu kolumn = zawsze przez --migrate z backupem.
- Po każdej zmianie kodu: pytest, commit, push.
- Raporty krótko: co zrobione, co nie i dlaczego.
