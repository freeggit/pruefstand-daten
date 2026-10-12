#!/usr/bin/env python3
"""Prüfstand – Status je Stufe eines Laufs (Verfassung V3.11, E29; Astra-Gutachten 4, Befund N09).

Läuft im Workflow «Prüfstand Suche» nach allen Stufen, auch wenn eine davon fehlgeschlagen ist (if: always()), und
vor dem Einchecken. Trägt in den Laufeintrag suche/laeufe/<Lauf-ID>.json und in suche/letzter_lauf.json ein, wie jede
Stufe ausging: «vollständig», «fehlgeschlagen», «übersprungen» oder «abgebrochen». Ein fehlgeschlagener oder
übersprungener Schritt erscheint so nie als aktuelle Ausgabe.

Eingang: Umgebungsvariablen STUFE_TESTS, STUFE_SIEGELTEST, STUFE_SUCHE, STUFE_ANALYSE, STUFE_FAMILIE_V mit dem Ergebnis
des jeweiligen Schritts laut GitHub (success, failure, skipped, cancelled). Aufruf: python lauf_status.py

V3.17 (12.10.2026; E38, Astra-Gutachten 15, G15-03): Ein Suchlauf ist nur «importierbar», wenn
  1. sein Vollarchiv per Ergebnis-Prüfsumme genau zu seinem Ergebnis passt und
  2. Tests und Siegeltest für genau diesen Prüfstand bestanden sind: im selben Lauf, oder in einem früheren Lauf mit
     identischer Prüfsumme aller geprüften Dateien (PRUEF_DATEIEN). Tests und Siegeltest laufen nur bei Code-Änderung.
Sonst gilt der Lauf als «teilweise» (TEIL) und wird nicht als Ergebnis importiert. Nur ein importierbarer Lauf wird
Referenz für E9 (letzter_eingabe_hash, letzter_gueltiger_lauf). «keine Neuberechnung» ist kein Ergebnis.
"""
import hashlib, json, os, sys
from datetime import datetime, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.environ.get("PS_LERNEN_DIR", os.path.join(ROOT, "_lernen"))
WORT = {"success": "vollständig", "failure": "fehlgeschlagen", "skipped": "übersprungen", "cancelled": "abgebrochen", "": "unbekannt"}
STUFEN = ("tests", "siegeltest", "suche", "analyse", "familie_v")
# Dateien, deren Änderung Tests und Siegeltest auslöst (Workflow suche.yml, push: paths), ohne verfassung.txt
PRUEF_DATEIEN = ("suchmaschine.py", "suche_lauf.py", "paare.txt", "mechanismen.txt", "siegel_test.py", "analyse.py", "vorreg.py",
                 "integritaet.py", "einchecken.py", "lauf_status.py", "eingabe.py", "korrekturen_neu.json", "explorativ.json",
                 ".github/workflows/suche.yml")


def pruef_hash(root=None):
    root = root or os.environ.get("PS_ROOT_DIR", ROOT)
    m = hashlib.sha256()
    for f in PRUEF_DATEIEN:
        p = os.path.join(root, f)
        m.update(f.encode()); m.update(hashlib.sha256(open(p, "rb").read()).digest() if os.path.exists(p) else b"-")
    return m.hexdigest()[:16]


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
    keine_neuberechnung = st.get("suche") == "keine Neuberechnung"
    for k, v in gh.items():
        if k == "suche" and st.get("suche") in ("vollständig", "fehlgeschlagen") and v in ("vollständig", "fehlgeschlagen") and v != st["suche"]:
            v = "fehlgeschlagen"   # widersprechen sich Skript und Workflow, gilt der Fehler
        if k == "suche" and keine_neuberechnung:
            continue   # V3.17 E9: Skript meldet «keine Neuberechnung», Workflow «success»
        if v != "unbekannt" or k not in st:
            st[k] = v
    if st.get("suche") != "vollständig":
        for k in ("analyse", "familie_v"):
            if st.get(k) in (None, "ausstehend", "unbekannt"):
                st[k] = "übersprungen"
    st["einchecken"] = "folgt (Ergebnis siehe Workflow; ein Laufeintrag auf claude/lernen belegt das gelungene Einchecken)"
    alle_ok = all(st.get(k) in ("vollständig", "übersprungen") for k in ("suche", "analyse", "familie_v")) and st.get("suche") == "vollständig"
    ip = os.path.join(LERNEN, "index.json")
    try:
        idx = json.load(open(ip, encoding="utf-8"))
    except (OSError, ValueError):
        idx = None
    idx = idx if isinstance(idx, dict) else None
    # V3.17 (E38): Freigabe des Ergebnisses
    ph = pruef_hash()
    if st.get("tests") == "vollständig" and st.get("siegeltest") == "vollständig":
        pruef = {"status": "bestanden in diesem Lauf", "pruef_hash": ph}
        if idx is not None:
            idx["pruefungen_bestanden"] = {"pruef_hash": ph, "lauf_id": lauf_id}
    elif st.get("tests") in ("fehlgeschlagen", "abgebrochen") or st.get("siegeltest") in ("fehlgeschlagen", "abgebrochen"):
        pruef = {"status": "nicht bestanden", "pruef_hash": ph}
    elif idx is not None and (idx.get("pruefungen_bestanden") or {}).get("pruef_hash") == ph:
        pruef = {"status": "bestanden für identischen Prüfstand", "pruef_hash": ph, "lauf": idx["pruefungen_bestanden"].get("lauf_id")}
    else:
        pruef = {"status": "kein Nachweis für diesen Prüfstand", "pruef_hash": ph}
    aus = eintrag.get("ausgaben") or {}
    archiv_ok = bool(eintrag.get("ergebnis_hash")) and aus.get("vollarchiv_ergebnis_hash") == eintrag.get("ergebnis_hash")
    pruef_ok = pruef["status"].startswith("bestanden")
    if keine_neuberechnung:
        gesamt = "keine Neuberechnung"
        e38 = {"importierbar": False, "grund": "keine Neuberechnung: kein neues Ergebnis (V3.17 §4)"}
    else:
        importierbar = bool(alle_ok and archiv_ok and pruef_ok)
        gruende = [g for g, ok_ in (("Suche oder Folgestufe nicht vollständig", alle_ok),
                                     ("Vollarchiv passt nicht per Ergebnis-Prüfsumme", archiv_ok),
                                     ("Tests/Siegeltest ohne Nachweis für diesen Prüfstand", pruef_ok)) if not ok_]
        e38 = {"importierbar": importierbar, "archiv_passend": archiv_ok, "pruefungen": pruef, "gruende": gruende}
        gesamt = ("vollständig" if importierbar else
                  "fehlgeschlagen" if st.get("suche") != "vollständig" else "teilweise")
        if importierbar and idx is not None:
            eg = (eintrag.get("e9") or {}).get("eingabe_hash_lauf")
            if eg:
                idx["letzter_eingabe_hash"] = eg
            idx["letzter_gueltiger_lauf"] = lauf_id
    eintrag.update({"stufen": st, "ende_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "gesamt": gesamt, "e38": e38})
    json.dump(eintrag, open(ep, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if letzter.get("lauf_id") == lauf_id:
        letzter.update({"stufen": st, "gesamt": eintrag["gesamt"]})
    else:
        letzter["letzter_versuch"] = {"lauf_id": lauf_id, "gesamt": eintrag["gesamt"], "stufen": st, "zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ")}
    json.dump(letzter, open(lp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if idx is not None:
        rel = f"suche/laeufe/{lauf_id}.json"
        lst = idx.setdefault("laeufe", [])
        e = next((x for x in lst if x.get("datei") == rel), None)
        if e is None:
            e = {"datei": rel, "lauf_id": lauf_id}; lst.append(e)
        e["gesamt"] = eintrag["gesamt"]
        e["importierbar"] = e38.get("importierbar")
        json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    print(f"Lauf {lauf_id}: {eintrag['gesamt']} – " + ", ".join(f"{k} {v}" for k, v in st.items() if k != "einchecken"))
    return 0


if __name__ == "__main__":
    sys.exit(main())
