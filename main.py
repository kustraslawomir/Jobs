"""Zbiera oferty, odsiewa duplikaty, liczy ATS match, dopisuje nowe do Google Sheets.

  python main.py --init      # jednorazowo: przygotuj arkusz
  python main.py             # normalny run (to odpala GitHub Actions)
  python main.py --dry-run   # bez Sheets: słownik z skills.csv, wynik na ekran
"""
import argparse
import csv
import datetime as dt
import os
import sys
import requests
import yaml

import ats
from dedup import Deduper, looks_like_agency
from sources import REGISTRY
from sources import nofluffjobs

DETAILS = {"nofluffjobs": nofluffjobs.details if nofluffjobs.FETCH_DETAILS else None}


def passes_filters(o, f, fx) -> str | None:
    t = o.title.lower()
    if not any(k in t for k in f["title_any"]):
        return "tytuł spoza zakresu"
    if any(k in t for k in f["title_exclude"]):
        return "wykluczone słowo w tytule"
    if f.get("remote_only") and o.remote is False:
        return "nie remote"
    top = o.salary_to_pln_month(fx)
    if f.get("min_salary_to_pln") and top is not None and top < f["min_salary_to_pln"]:
        return "za niskie widełki"
    return None


def notify(cfg, offers):
    tok, chat = os.environ.get("TELEGRAM_TOKEN"), os.environ.get("TELEGRAM_CHAT_ID")
    if not (cfg["notify"].get("telegram") and tok and chat):
        return
    good = [o for o in offers if (o.match or 0) >= cfg["notify"]["min_match_to_notify"]]
    if not good:
        return
    lines = [f"🆕 {len(good)} nowych ofert (match ≥ {cfg['notify']['min_match_to_notify']:.0%}):"]
    for o in sorted(good, key=lambda x: -(x.match or 0))[:15]:
        lines.append(f"• {o.match:.0%} {o.company} – {o.title}\n  {o.salary_text()}\n  {o.url}")
    requests.post(f"https://api.telegram.org/bot{tok}/sendMessage",
                  json={"chat_id": chat, "text": "\n".join(lines), "disable_web_page_preview": True}, timeout=20)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--init", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    cfg = yaml.safe_load(open("config.yaml", encoding="utf-8"))
    cv_text = open("cv.txt", encoding="utf-8").read()

    if args.dry_run:
        with open("skills.csv", encoding="utf-8") as fh:
            skill_rows = list(csv.reader(fh))[1:]
        existing, last_row, ws = [], 1, None
    else:
        import sheets
        sh = sheets.connect()
        if args.init:
            sheets.init(sh, cfg)
            print("Arkusz gotowy.")
            return
        ws = sh.worksheet(cfg["sheet"]["tab_offers"])
        skill_rows = sheets.read_skills(sh, cfg)
        existing, last_row = sheets.read_existing(ws)

    skills = ats.load_skills(skill_rows)
    dd = Deduper(existing, cfg["dedup"]["fuzzy_title_threshold"])
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (job-tracker; personal use)"

    new, stats, errors = [], {}, []
    for name, enabled in cfg["sources"].items():
        if not enabled or name not in REGISTRY:
            continue
        try:
            offers = REGISTRY[name](session)
        except Exception as e:                       # jedno źródło padło -> reszta działa
            errors.append(f"{name}: {e}")
            continue
        st = stats.setdefault(name, {"pobrane": len(offers), "nowe": 0})
        for o in offers:
            reason = passes_filters(o, cfg["filters"], cfg["fx_to_pln"]) or dd.check(o)
            if reason:
                st[reason] = st.get(reason, 0) + 1
                continue
            detail_fn = DETAILS.get(name)
            if detail_fn:
                try:
                    o.description = detail_fn(session, o)
                except Exception:
                    pass
            o.match, o.gaps, o.add_to_cv = ats.evaluate(o.description, skills, cv_text)
            if cfg["filters"].get("min_match") and o.match is not None and o.match < cfg["filters"]["min_match"]:
                st["za niski match"] = st.get("za niski match", 0) + 1
                continue
            if looks_like_agency(o.company):
                o.note = "Agencja? Ustal klienta końcowego, zanim wyślesz CV."
            dd.add(o)
            new.append(o)
            st["nowe"] += 1

    today = dt.date.today().isoformat()
    if args.dry_run:
        for o in new:
            m = f"{o.match:.0%}" if o.match is not None else "–"
            print(f"{m:>5}  {o.company} – {o.title} | {o.salary_text()} | luki: {', '.join(o.gaps) or '-'}")
    else:
        import sheets
        sheets.append_offers(ws, new, today, last_row)
        notify(cfg, new)

    print("Statystyki:", stats)
    if errors:
        print("BŁĘDY ŹRÓDEŁ (sprawdź endpointy w DevTools):", *errors, sep="\n  ")
        # żeby GitHub wysłał maila o nieudanym runie, gdy WSZYSTKIE źródła padły
        if not stats:
            sys.exit(1)


if __name__ == "__main__":
    main()
