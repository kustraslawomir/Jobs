"""Zbiera oferty, odsiewa duplikaty, liczy ATS match, dopisuje nowe do Google Sheets.

  python main.py --init      # jednorazowo: przygotuj arkusz
  python main.py             # normalny run (to odpala GitHub Actions)
  python main.py --dry-run   # bez Sheets: słownik z skills.csv, wynik na ekran
"""
import argparse
import csv
import datetime as dt
import os
import re
import sys
import requests
import yaml

import ats
from dedup import Deduper, SURE_BY_CONTENT, looks_like_agency, norm_description
from sources import REGISTRY
from sources import justjoinit, nofluffjobs

DETAILS = {"nofluffjobs": nofluffjobs.details if nofluffjobs.FETCH_DETAILS else None,
           "justjoinit": justjoinit.details}


def _has_word(title: str, word: str) -> bool:
    return re.search(rf"(?<!\w){re.escape(word)}(?!\w)", title) is not None


def title_reason(title: str, f) -> str | None:
    t = title.lower()
    in_scope = (any(k in t for k in f["title_require_any"])
                or (any(k in t for k in f["title_mobile_words"]) and any(k in t for k in f["title_dev_words"])))
    if not in_scope:
        return "tytuł spoza zakresu"
    if any(_has_word(t, k) for k in f["title_exclude"]):
        return "wykluczone słowo w tytule"
    return None


def passes_filters(o, f, fx) -> str | None:
    reason = title_reason(o.title, f)
    if reason:
        return reason
    if f.get("remote_only") and o.remote is not True:
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
        existing, last_row, ws, descriptions = [], 1, None, {}
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
        descriptions = sheets.read_descriptions(sh, cfg)

    skills = ats.load_skills(skill_rows)
    dd = Deduper(existing, descriptions, cfg["dedup"], cfg["fx_to_pln"])
    session = requests.Session()
    session.headers["User-Agent"] = "Mozilla/5.0 (job-tracker; personal use)"

    new, stats, errors, events = [], {}, [], []
    for name, enabled in cfg["sources"].items():
        if not enabled or name not in REGISTRY:
            continue
        try:
            offers = REGISTRY[name](session)
        except Exception as e:                       # jedno źródło padło -> reszta działa
            errors.append(f"{name}: {e}")
            continue
        st = stats.setdefault(name, {"pobrane": len(offers), "nowe": 0})
        detail_fn = DETAILS.get(name)
        for o in offers:
            if dd.has_key(o):
                st["to samo ID"] = st.get("to samo ID", 0) + 1
                continue
            reason = passes_filters(o, cfg["filters"], cfg["fx_to_pln"])
            if reason:
                st[reason] = st.get(reason, 0) + 1
                continue
            if detail_fn:
                try:
                    o.description = detail_fn(session, o)
                except Exception:
                    pass                                    # zostaje opis z listy
            verdict = dd.check(o)
            if verdict.rejected:
                m = verdict.rejected
                st[m.reason] = st.get(m.reason, 0) + 1
                events.append(("DUP", f"[{m.reason}] {m.describe(o)}", m.reason))
                continue
            for m in verdict.matches:
                label = "agencja" if m.kind == "agency" else "możliwy duplikat"
                st[f"z notatką: {label}"] = st.get(f"z notatką: {label}", 0) + 1
                events.append(("AGENCJA" if m.kind == "agency" else "MOŻLIWY", m.describe(o), ""))
            o.match, o.gaps, o.add_to_cv, o.n_req = ats.evaluate(o.description, skills, cv_text)
            if cfg["filters"].get("min_match") and o.match is not None and o.match < cfg["filters"]["min_match"]:
                st["za niski match"] = st.get("za niski match", 0) + 1
                continue
            notes = list(verdict.notes)
            if o.n_req < ats.MIN_REQUIREMENTS:
                notes.append("Mało danych do ATS – sprawdź opis ręcznie")
            if looks_like_agency(o.company) and not any(m.kind == "agency" for m in verdict.matches):
                notes.append("Agencja? Ustal klienta końcowego, zanim wyślesz CV.")
            o.note = ". ".join(notes)
            dd.add(o)
            new.append(o)
            st["nowe"] += 1

    today = dt.date.today().isoformat()
    if args.dry_run:
        for o in new:
            m = f"{o.match:.0%}" if o.match is not None else "–"
            print(f"{m:>5}  {o.company} – {o.title} | {o.salary_text()} | wym.: {o.n_req} | luki: {', '.join(o.gaps) or '-'}")
    else:
        import sheets
        sheets.append_offers(ws, new, today, last_row)
        sheets.append_descriptions(sh, cfg, [(o.key, norm_description(o.description)) for o in new])
        notify(cfg, new)

    print("Statystyki:", stats)
    if args.dry_run:
        sure = [e for e in events if e[0] == "DUP"]
        only_content = sum(1 for e in sure if e[2] == SURE_BY_CONTENT)
        print(f"Pewne duplikaty: {len(sure)} (w tym złapane tylko po treści: {only_content})")
        for kind, title in (("DUP", "Odrzucone duplikaty"), ("MOŻLIWY", "Możliwe duplikaty (oferta zostaje, z notatką)"),
                            ("AGENCJA", "Notatki agencyjne (oferta zostaje)")):
            lines = [f"{kind} {e[1]}" for e in events if e[0] == kind]
            print(f"{title}: {len(lines)}" + (" (max 30)" if len(lines) > 30 else ""), *lines[:30], sep="\n  " if lines else "")
    if errors:
        print("BŁĘDY ŹRÓDEŁ (sprawdź endpointy w DevTools):", *errors, sep="\n  ")
        # żeby GitHub wysłał maila o nieudanym runie, gdy WSZYSTKIE źródła padły
        if not stats:
            sys.exit(1)


if __name__ == "__main__":
    main()
