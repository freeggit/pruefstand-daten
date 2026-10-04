#!/usr/bin/env python3
"""Prüfstand – Status je Stufe eines Laufs (Verfassung V3.11, E29; Astra-Gutachten 4, Befund N09).

Läuft im Workflow «Prüfstand Suche» nach allen Stufen, auch wenn eine davon fehlgeschlagen ist (if: always()), und
vor dem Einchecken. Trägt in den Laufeintrag suche/laeufe/<Lauf-ID>.json und in suche/letzter_lauf.json ein, wie jede
Stufe ausging: «vollständig», «fehlgeschlagen», «übersprungen» oder «abgebrochen». Ein fehlgeschlagener oder
übersprungener Schritt erscheint so nie als aktuelle Ausgabe.

Eingang: Umgebungsvariablen STUFE_TESTS, STUFE_SIEGELTEST, STUFE_SUCHE, STUFE_ANALYSE, STUFE_FAMILIE_V mit dem Ergebnis
des jeweiligen Schritts laut GitHub (success, failure, skipped, cancelled). Aufruf: python lauf_status.py
"""
import json, os, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.environ.get("PS_LERNEN_DIR", os.path.join(ROOT, "_lernen"))
WORT = {"success": "vollständig", "failure": "fehlgeschlagen", "skipped": "übersprungen", "cancelled": "abgebrochen", "": "unbekannt"}
STUFEN = ("tests", "siegeltest", "suche", "analyse", "familie_v")


def main():
    jetzt = datetime.now(timezone.utc)
    gh = {st: WORT.get(os.environ.get("STUFE_" + st.upper(), ""), os.environ.get("STUFE_" + st.upper(), "")) for st in STUFEN}
    os.makedirs(os.path.join(LERNEN, "suche", "laeufe"), exist_ok=True)
    lp = os.path.join(LERNEN, "suche", "letzter_lauf.json")
    try:
        letzter = json.load(open(lp, encoding="utf-8"))
    except (OSError, ValueError):
        letzter = {}
    run = os.environ.get("GITHUB_RUN_ID")
    lauf_id, eintrag, ep = None, None, None
    # Der Laufeintrag dieses Versuchs: der jüngste Eintrag mit derselben github_run_id (oder, lokal, der jüngste überhaupt)
    for name in sorted(os.listdir(os.path.join(LERNEN, "suche", "laeufe")), reverse=True):
        if not name.endswith(".json"):
            continue
        p = os.path.join(LERNEN, "suche", "laeufe", name)
        try:
            e = json.load(open(p, encoding="utf-8"))
        except (OSError, ValueError):
            continue
        if run is None or e.get("github_run_id") == run:
            lauf_id, eintrag, ep = e.get("lauf_id"), e, p
            break
    if eintrag is None:
        # Die Suche ist gescheitert, bevor sie einen Eintrag schreiben konnte: Der Versuch wird trotzdem festgehalten.
        lauf_id = "L" + jetzt.strftime("%Y%m%dT%H%M%SZ")
        ep = os.path.join(LERNEN, "suche", "laeufe", f"{lauf_id}.json")
        eintrag = {"lauf_id": lauf_id, "github_run_id": run, "anlass": os.environ.get("GITHUB_EVENT_NAME", "lokal"),
                   "beginn_utc": None, "stufen": {}, "ausgaben": None,
                   "hinweis": "Kein Laufeintrag der Suche gefunden: Der Lauf endete vor dem Schreiben eines Ergebnisses."}
    st = dict(eintrag.get("stufen") or {})
    for k, v in gh.items():
        if k == "suche" and st.get("suche") in ("vollständig", "fehlgeschlagen") and v in ("vollständig", "fehlgeschlagen") and v != st["suche"]:
            v = "fehlgeschlagen"   # widersprechen sich Skript und Workflow, gilt der Fehler
        if v != "unbekannt" or k not in st:
            st[k] = v
    if st.get("suche") != "vollständig":
        for k in ("analyse", "familie_v"):
            if st.get(k) in (None, "ausstehend", "unbekannt"):
                st[k] = "übersprungen"
    st["einchecken"] = "folgt (Ergebnis siehe Workflow; ein Laufeintrag auf claude/lernen belegt das gelungene Einchecken)"
    alle_ok = all(st.get(k) in ("vollständig", "übersprungen") for k in ("suche", "analyse", "familie_v")) and st.get("suche") == "vollständig"
    eintrag.update({"stufen": st, "ende_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                    "gesamt": "vollständig" if alle_ok else ("fehlgeschlagen" if st.get("suche") != "vollständig" else "teilweise")})
    json.dump(eintrag, open(ep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if letzter.get("lauf_id") == lauf_id:
        letzter.update({"stufen": st, "gesamt": eintrag["gesamt"]})
    else:
        letzter["letzter_versuch"] = {"lauf_id": lauf_id, "gesamt": eintrag["gesamt"], "stufen": st, "zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ")}
    json.dump(letzter, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = os.path.join(LERNEN, "index.json")
    try:
        idx = json.load(open(ip, encoding="utf-8"))
    except (OSError, ValueError):
        idx = None
    if isinstance(idx, dict):
        rel = f"suche/laeufe/{lauf_id}.json"
        lst = idx.setdefault("laeufe", [])
        e = next((x for x in lst if x.get("datei") == rel), None)
        if e is None:
            e = {"datei": rel, "lauf_id": lauf_id}; lst.append(e)
        e["gesamt"] = eintrag["gesamt"]
        json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Lauf {lauf_id}: {eintrag['gesamt']} – " + ", ".join(f"{k} {v}" for k, v in st.items() if k != "einchecken"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
