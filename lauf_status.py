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

V3.18 (E9 Stufe 2, ENTWURF 27.10.2026): Referenz ist eingabe_hash_nach_eintragung (Eingabe nach der eigenen
Registereintragung des Laufs), falls vorhanden; sonst wie bisher eingabe_hash_lauf. §6: Scheitern Tests oder Siegeltest
(z. B. im Kontrolllauf am Montag), wird der gespeicherte Nachweis für diesen Prüfstand entzogen.
Fassung 2 (28.10.2026, Astra-Gutachten 23, M4): Der Prüfstand umfasst auch die Testdateien und die tatsächlich
gebundene Rechenumgebung (Python, numpy, pandas, python-dateutil, tzdata, NPY_DISABLE_CPU_FEATURES). Ein Lauf, der eine
nicht eingefrorene Datei liest (Ausnahmepfad), gilt nur, wenn der Siegeltest des Nachweises genau diese Datei über den
Stand geprüft hat (siegel_abdeckung.json). Aufruf mit --nachweis: meldet dem Workflow, ob für den aktuellen Prüfstand ein
gültiger Nachweis vorliegt (sonst laufen Tests und Siegeltest zuerst; Soll aus Gutachten 23).
"""
import hashlib, json, os, sys
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.environ.get("PS_LERNEN_DIR", os.path.join(ROOT, "_lernen"))
WORT = {"success": "vollständig", "failure": "fehlgeschlagen", "skipped": "übersprungen", "cancelled": "abgebrochen", "": "unbekannt"}
STUFEN = ("tests", "siegeltest", "suche", "analyse", "familie_v")
# Dateien, deren Änderung Tests und Siegeltest auslöst (Workflow suche.yml, push: paths), ohne verfassung.txt
PRUEF_DATEIEN = ("suchmaschine.py", "suche_lauf.py", "paare.txt", "mechanismen.txt", "siegel_test.py", "analyse.py", "vorreg.py",
                 "integritaet.py", "einchecken.py", "lauf_status.py", "eingabe.py", "korrekturen_neu.json", "explorativ.json",
                 ".github/workflows/suche.yml",
                 "discovery.py", "nachfuehrung.json",   # V3.18 E9 (Entwurf); im Workflow unter push: paths
                 "test_einchecken.py", "test_integritaet.py", "test_lauf_status.py", "test_discovery.py")   # Gutachten 23, M4
UMGEBUNG_PAKETE = ("numpy", "pandas", "python-dateutil", "tzdata")
MAX_ALTER_TAGE = 7   # Soll aus Gutachten 23: spätestens nach 7 Tagen laufen Tests und Siegeltest erneut
NUR_VERMERKT = ("ImageOS", "ImageVersion")   # Rechner-Abbild: vermerkt, nicht Teil des Prüfstands (siehe umgebung)
# V3.18 §6 (Option): Der Workflow setzt PS_PAR6=1, wenn Reto §6 angenommen hat. Nur dann gilt der Nachweis über
# Eingabeänderungen hinweg ausdrücklich nach §6 und ist an die tatsächliche Rechenumgebung gebunden (M4); Tests und
# Siegeltest laufen dann auch montags und ohne gültigen Nachweis. Ohne §6 gilt E38 wie in V3.17 (Prüfstand = Dateien).
PAR6 = os.environ.get("PS_PAR6") == "1"


def umgebung():
    """Gutachten 23, M4: die in diesem Lauf tatsächlich vorliegende Rechenumgebung. Festgeschrieben sind in suche.yml
    Python, numpy, pandas und die CPU-Einstellung; python-dateutil und tzdata werden hier erfasst. Ändert sich etwas davon,
    ist der Prüfstand neu und wird neu geprüft (mit §6). Das Abbild des GitHub-Rechners (ImageOS, ImageVersion) wird nur
    vermerkt, nicht in die Prüfsumme genommen: Das Betriebssystem ist über runs-on fest; das Abbild wechselt wöchentlich
    und bei der schrittweisen Verteilung von Lauf zu Lauf. Abweichungen in der letzten Stelle zeigt der Kontrolllauf."""
    from importlib import metadata
    u = {"python": sys.version.split()[0], "NPY_DISABLE_CPU_FEATURES": os.environ.get("NPY_DISABLE_CPU_FEATURES", ""),
         "ImageOS": os.environ.get("ImageOS"), "ImageVersion": os.environ.get("ImageVersion")}
    for p in UMGEBUNG_PAKETE:
        try:
            u[p] = metadata.version(p)
        except Exception:
            u[p] = None
    return u


def pruef_hash(root=None, umg=None, mit_umgebung=None):
    """Prüfsumme des Prüfstands: Inhalt aller PRUEF_DATEIEN (Code, Tests, Workflow, Lese- und Stichtagseinstellungen
    in discovery.py und suchmaschine.py), mit §6 zusätzlich die tatsächlich vorliegende Rechenumgebung (M4)."""
    root = root or os.environ.get("PS_ROOT_DIR", ROOT)
    m = hashlib.sha256()
    for f in PRUEF_DATEIEN:
        p = os.path.join(root, f)
        m.update(f.encode()); m.update(hashlib.sha256(open(p, "rb").read()).digest() if os.path.exists(p) else b"-")
    if PAR6 if mit_umgebung is None else mit_umgebung:
        u = umgebung() if umg is None else umg
        m.update(json.dumps({k: v for k, v in u.items() if k not in NUR_VERMERKT}, sort_keys=True).encode())
    return m.hexdigest()[:16]


def nachweis(idx, ph):
    """Gespeicherter Nachweis für genau diesen Prüfstand, sofern kein jüngeres Scheitern ihn entzogen hat. Ein älterer
    Nachweis, den einchecken.py beim Dreiweg-Mischen von index.json zurückbringt, gilt nicht. Verglichen wird der Zeitpunkt
    der Prüfung (auch bei einem erneuten Versuch desselben GitHub-Laufs mit alter Lauf-ID); ältere Einträge ohne Zeitpunkt
    über die Lauf-ID."""
    b = (idx or {}).get("pruefungen_bestanden") or {}
    g = (idx or {}).get("pruefungen_gescheitert") or {}
    if b.get("pruef_hash") != ph:
        return None
    if g.get("pruef_hash") == ph:
        if (g.get("zeit_utc") and b.get("zeit_utc")):
            if str(g["zeit_utc"]) >= str(b["zeit_utc"]):
                return None
        elif str(g.get("lauf_id") or "") >= str(b.get("lauf_id") or ""):
            return None
    return b


def siegel_abdeckung(root=None):
    """Gutachten 23, M4: nicht eingefrorene Dateien, die der Siegeltest dieses Laufs über den Stand geprüft hat."""
    p = os.environ.get("PS_SIEGEL_ABDECKUNG") or os.path.join(root or os.environ.get("PS_ROOT_DIR", ROOT), "siegel_abdeckung.json")
    try:
        d = json.load(open(p, encoding="utf-8"))
    except (OSError, ValueError):
        return None
    if not isinstance(d, dict) or d.get("bestanden") is not True:   # nur ein bestandener Siegeltest deckt ab
        return None
    a = d.get("ausnahmen_abgedeckt")
    return sorted(a) if isinstance(a, list) else None


def ausnahmen_des_laufs(eintrag):
    """Nicht eingefrorene Dateien, welche die Suche in diesem Lauf ungekürzt aus dem Spiegel las (Ausnahmepfad)."""
    st = ((eintrag or {}).get("e9") or {}).get("stand") or {}
    return sorted({x.get("datei") for x in (st.get("nicht_eingefroren") or []) if isinstance(x, dict) and x.get("datei")})


def nachweis_cli():
    """Für den Workflow (Schritt «Prüfnachweis»): gueltig=true/false nach GITHUB_OUTPUT. Scheitert nie."""
    try:
        idx = json.load(open(os.path.join(LERNEN, "index.json"), encoding="utf-8"))
    except (OSError, ValueError):
        idx = None
    try:
        ph = pruef_hash()
        idx = idx if isinstance(idx, dict) else None
        b = None if (idx or {}).get("ausnahmen_ohne_siegel") else nachweis(idx, ph)
        if b and not str(b.get("zeit_utc") or "") >= (datetime.now(timezone.utc) - timedelta(days=MAX_ALTER_TAGE)).strftime("%Y-%m-%dT%H:%MZ"):
            print(f"Nachweis aus Lauf {b.get('lauf_id')} ist älter als {MAX_ALTER_TAGE} Tage oder ohne Zeitpunkt")
            b = None   # Gutachten 23 (Soll): die wöchentliche Prüfung hängt nicht am Montagslauf
        print(f"Prüfstand {ph}: " + (f"gültiger Nachweis aus Lauf {b.get('lauf_id')}" if b else "kein gültiger Nachweis; Tests und Siegeltest laufen"))
    except Exception as ex:   # im Zweifel prüfen
        b = None
        print(f"Prüfnachweis nicht bestimmbar ({ex}); Tests und Siegeltest laufen")
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"gueltig={'true' if b else 'false'}\n")
    return 0


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
    umg = umgebung()
    ph = pruef_hash(umg=umg)
    abd, b_ = None, None
    e9_ = eintrag.get("e9") or {}
    eg_tats = e9_.get("eingabe_hash_lauf") or e9_.get("eingabe_hash")   # tatsächliche Eingabe dieses Laufs (vor der Rechnung)
    if st.get("tests") == "vollständig" and st.get("siegeltest") == "vollständig":
        abd = siegel_abdeckung()
        pruef = {"status": "bestanden in diesem Lauf", "pruef_hash": ph}
        if idx is not None:   # Fassung 2: mit Zeitpunkt und der Eingabe, auf der geprüft wurde (Finalistenregel)
            idx["pruefungen_bestanden"] = {"pruef_hash": ph, "lauf_id": lauf_id, "zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"),
                                           "eingabe_hash": eg_tats, "umgebung": umg, "ausnahmen_abgedeckt": abd}
            idx.pop("pruefungen_gescheitert", None)
    elif st.get("tests") in ("fehlgeschlagen", "abgebrochen") or st.get("siegeltest") in ("fehlgeschlagen", "abgebrochen"):
        pruef = {"status": "nicht bestanden", "pruef_hash": ph}
        if idx is not None:   # V3.18 §6 (Entwurf): Ein gescheiterter Test entzieht den Nachweis für diesen Prüfstand
            if (idx.get("pruefungen_bestanden") or {}).get("pruef_hash") == ph:
                idx.pop("pruefungen_bestanden")
            idx["pruefungen_gescheitert"] = {"pruef_hash": ph, "lauf_id": lauf_id, "zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")}
    else:
        # V3.18 §6 (Entwurf): ein jüngeres Scheitern für denselben Prüfstand gilt, auch wenn einchecken.py beim Dreiweg-Mischen
        # von index.json einen älteren Nachweis zurückbringt (Vergleich über den Zeitpunkt, siehe nachweis)
        b_ = nachweis(idx, ph)
        if b_:
            abd = b_.get("ausnahmen_abgedeckt")
            pruef = {"status": "bestanden für identischen Prüfstand", "pruef_hash": ph, "lauf": b_.get("lauf_id")}
        else:
            pruef = {"status": "kein Nachweis für diesen Prüfstand", "pruef_hash": ph}
    # Gutachten 23, M4 (mit §6): Ein Lauf über den Ausnahmepfad (nicht eingefrorene Datei) gilt nur mit passendem Siegelnachweis
    aus_ = ausnahmen_des_laufs(eintrag)
    ohne_siegel = sorted(set(aus_) - set(abd or [])) if (PAR6 and pruef["status"].startswith("bestanden")) else []
    if ohne_siegel:
        pruef = dict(pruef, status="kein Nachweis: nicht eingefrorene Datei ohne Siegelnachweis über den Stand",
                     ausnahmen_ohne_siegel=ohne_siegel[:20])
    pruef["umgebung"] = umg
    if idx is not None:   # meldet dem nächsten Lauf (--nachweis), dass Tests und Siegeltest zuerst laufen sollen
        if ohne_siegel:
            idx["ausnahmen_ohne_siegel"] = {"lauf_id": lauf_id, "dateien": ohne_siegel[:20]}
        elif pruef["status"].startswith("bestanden"):
            idx.pop("ausnahmen_ohne_siegel", None)
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
        # Retos Entscheid vom 15.10.2026 (V3.18 §6, Gutachten 23): Ein Finalist braucht bestandene Prüfungen im selben Lauf
        # oder einen Nachweis mit identischer tatsächlicher Eingabe-Prüfsumme; der Vergleichsstand nach §4 zählt nicht.
        fin = bool(importierbar and (pruef["status"] == "bestanden in diesem Lauf" or
                                     (pruef["status"] == "bestanden für identischen Prüfstand" and eg_tats
                                      and (b_ or {}).get("eingabe_hash") == eg_tats)))
        # Ohne §6 bleibt es bei Retos Entscheid vom 15.10.2026: Ein Nachweis aus einem Lauf mit anderer Eingabe erfüllt E38 nicht;
        # der Lauf wird mit Vorbehalt importiert (ohne Wirkung, solange es keinen Finalisten gibt). Mit §6 ist das die
        # ausdrückliche Ausnahme zu E38 für reguläre Explorationsläufe.
        geliehen = (importierbar and pruef["status"] == "bestanden für identischen Prüfstand"
                    and (b_ or {}).get("eingabe_hash") != eg_tats)
        e38 = {"importierbar": importierbar, "archiv_passend": archiv_ok, "pruefungen": pruef, "gruende": gruende,
               "nachweis_bei_geaenderter_eingabe": (None if not geliehen else
                                                    "Ausnahme nach V3.18 §6 (regulärer Explorationslauf)" if PAR6 else
                                                    "Vorbehalt: E38 nicht erfüllt, Nachweis aus Lauf mit anderer Eingabe (Reto 15.10.2026)"),
               "finalist_zulaessig": fin,
               "finalist_regel": ("Finalist nur mit Prüfungen im selben Lauf oder mit einem Nachweis auf identischer tatsächlicher "
                                  "Eingabe-Prüfsumme (eingabe_hash_lauf); Reto 15.10.2026")}
        gesamt = ("vollständig" if importierbar else
                  "fehlgeschlagen" if st.get("suche") != "vollständig" else "teilweise")
        if importierbar and idx is not None:
            # V3.18 E9 (Entwurf): Referenz ist der Stand nach der eigenen Registereintragung, sonst wie bisher die Eingabe des Laufs
            eg = e9_.get("eingabe_hash_nach_eintragung") or e9_.get("eingabe_hash_lauf")
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
    sys.exit(nachweis_cli() if "--nachweis" in sys.argv[1:] else main())
