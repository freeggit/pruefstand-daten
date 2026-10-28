#!/usr/bin/env python3
"""Prüfstand – Suchlauf in der GitHub Action (Methode M4; Verfassungsversion aus verfassung.txt).

V3.11 (E29, 4.10.2026, Reto: «ok, gerne freigeben»; Astra-Gutachten 4, Befund N09): Jeder Ausführungsversuch erhält eine
Lauf-ID und einen Laufeintrag suche/laeufe/<Lauf-ID>.json – auch ohne neue Hypothesen und auch bei einem Fehler der
Suchmaschine: Datenstand, Beginn, Ende, Status je Stufe, vorhandene sowie gegenüber dem Vorlauf entfallene und neue
Reihen, Prüfsumme der Ergebnisse, Verweis auf die Ausgaben. Ein S####-Dokument entsteht bei neuen Hypothesen, bei
geändertem Code ODER bei geänderten Ergebnissen (Prüfsumme). Das Vollarchiv S####_alle.csv.gz (rund 10 MB) entsteht nur
bei neuen Hypothesen oder geändertem Code; sonst verweist der Laufeintrag auf das letzte Vollarchiv (die Schlüssel
stehen im Register). Den Status der Stufen Analyse, Familie V und Einchecken trägt lauf_status.py nach.

Liest den Stand auf dem Zweig claude/lernen (Arbeitskopie _lernen), rechnet die Suchmaschine auf den lokalen
Kopien von main, claude/daten-energie und claude/daten-neu und legt das Ergebnis auf claude/lernen ab:
  suche/S####.json (Format wie bisher, plus Felder V3.4), suche/S####_ueberlebende.csv, suche/S####_log.txt,
  hypothesen.txt.gz (Register V3.3), index.json (kumuliert, suchlaeufe, reihen_letzter_suchlauf).
Ein S####-Eintrag entsteht bei neuen Hypothesen ODER geändertem Code (Suchmaschine, paare.txt, mechanismen.txt). Jeder Lauf schreibt
zusätzlich suche/letzter_lauf.json mit Commit-IDs aller Zweige und Prüfsummen (Nachvollziehbarkeit, V3.6).
Die Routine «Prüfstand Lernrunde» rechnet nicht mehr selbst; sie liest diese Dateien und schreibt den Lernbericht.

V3.17 (12.10.2026, Reto: «freigeben»; Astra-Gutachten 15 und 16):
- §4 (E9 neu): Bei geplanten Läufen (PS_E9=1) rechnet die Suchmaschine zuerst nur die Eingabe-Prüfsumme der Discovery.
  Gerechnet wird nur bei geänderter Eingabe, ohne gültigen Referenzlauf oder am Montag (Kontrolllauf, gleiche Seeds).
  Sonst entsteht ein Laufeintrag «keine Neuberechnung» mit Verweis auf den letzten gültigen Lauf.
- §5 (E38): Ein Vollarchiv entsteht auch bei geänderten Ergebnissen; jeder Laufeintrag nennt die Ergebnis-Prüfsumme des
  Archivs, auf das er verweist. Die Freigabe (importierbar ja/nein) trägt lauf_status.py ein.

V3.18 (E9 Stufe 2, ENTWURF 27.10.2026, nicht in Kraft):
- Die Suchmaschine liest die Discovery-Daten aus dem eingefrorenen Stand _lernen/discovery (discovery.py). Jeder Lauf
  beginnt mit dem Eingabe-Durchgang: neue Dateien werden gekürzt und eingefroren, freigegebene Nachführungen
  (nachfuehrung.json) angewandt, Revisionen des Spiegels nur berichtet (discovery/revisionen.json). Danach prüft die
  Einfrierprüfung den ganzen Stand; bei einem Verstoss wird nicht gerechnet.
- Vergleichsstand nach der Registereintragung: Der Laufeintrag nennt zusätzlich eingabe_hash_nach_eintragung (neues
  Register, neue kumulierte Zahl). lauf_status.py setzt diesen Wert als Referenz, damit sich ein Lauf am Folgetag nicht
  selbst noch einmal auslöst.
Fassung 2 (28.10.2026, Astra-Gutachten 23):
- M1: Die Vorprüfung (Eingabe-Durchgang) hält genau eine Fassung von stand.json fest (Feld stand.fassung) und stellt
  daraus alle Dateien im Cache der Suchmaschine bereit (Feld stand.bereitgestellt). Die Rechnung liest ausschliesslich
  diese Dateien (ohne Einfrieren, ohne Nachführung). Danach muss gelten: gleiche Fassung, bereitgestellte Dateien
  unverändert, keine weiteren Dateien, gleiche Eingabe-Prüfsumme wie in der Vorprüfung. Scheitert die Vorprüfung
  (unlesbare Pflicht-Eingabe, Familie L nicht lesbar, Verstoss in der Einfrierprüfung), wird vor der Rechnung
  abgebrochen; der Lauf ist fehlgeschlagen.
- M2: eingabe_hash_lauf ist die tatsächliche Eingabe der Rechnung (E38, Finalisten) und bleibt unverändert;
  eingabe_hash_nach_eintragung dient nur dem Auslöser (gleiche Definition, nur die eigenen Änderungen eingerechnet).
  eingabe_hash_lauf ist die Prüfsumme der Vorprüfung, also vor der Rechnung gesichert. Der Kontrolllauf am Montag
  vergleicht Ergebnis-Prüfsumme und Entscheidungs-Prüfsumme (Positivliste in eingabe.py: Placebo-Pfad, Hürden, Route C,
  Kandidaten der Stufe D, Kalibrierung). Register und kumulierte Zahl gehen nicht in Entscheidungen ein (nur Kennzeichen
  «neu», Zähler und Bonferroni-Bericht), solange mindestens 40 Placebo-Läufe rechnen (Betrieb: 200).
"""
import gzip, hashlib, json, os, shutil, subprocess, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from integritaet import ohne_nan  # noqa: E402
try:
    from eingabe import entscheidung_pruefsumme  # noqa: E402  (V3.18 Fassung 2)
except ImportError:   # eingabe.py noch ohne die Funktion (Dateien einzeln hochgeladen): keine Entscheidungs-Prüfsumme
    def entscheidung_pruefsumme(z):
        return None
try:
    import discovery  # noqa: E402  (V3.18 E9, Entwurf: eingefrorener Discovery-Stand)
except ImportError:   # Code noch nicht vollständig hochgeladen: wie bisher ohne Stand
    discovery = None
STAND_AKTIV = bool(discovery is not None and getattr(discovery, "AKTIV", False))   # Rückweg: discovery.AKTIV = False

def schreibe_json(obj, pfad):
    """Strenges JSON: NaN und unendliche Werte werden zu null (5.10.2026, Reto: «NaN-Korrektur wie vorgeschlagen»).
    Anlass: S0022 enthielt NaN in bausteine[0].t_bestaetigung_etf und liess sich nicht in die Datenbank übernehmen."""
    with open(pfad, "w", encoding="utf-8") as f:
        json.dump(ohne_nan(obj), f, ensure_ascii=False, indent=1, allow_nan=False)

LERNEN = os.path.join(ROOT, "_lernen")
LAUF = os.environ.get("PS_LAUF", "/tmp/lauf")
os.makedirs(LAUF, exist_ok=True)
os.makedirs(os.path.join(LERNEN, "suche", "laeufe"), exist_ok=True)
BEGINN = datetime.now(timezone.utc)
LAUF_ID = "L" + BEGINN.strftime("%Y%m%dT%H%M%SZ")
try:
    VERFASSUNG = open(os.path.join(ROOT, "verfassung.txt"), encoding="utf-8").read().split()[0]
except (OSError, IndexError):
    VERFASSUNG = "unbekannt (verfassung.txt fehlt)"

def commit(pfad):
    try:
        return subprocess.run(["git", "-C", pfad, "rev-parse", "HEAD"], capture_output=True, text=True).stdout.strip() or None
    except Exception:
        return None

def sha(pfad):
    try:
        return hashlib.sha256(open(pfad, "rb").read()).hexdigest()[:16]
    except Exception:
        return None

def datenstand():
    return {"commit_main": commit(ROOT), "commit_energie": commit(os.path.join(ROOT, "_daten-energie")),
            "commit_neu": commit(os.path.join(ROOT, "_daten-neu")),
            "sha_manifest_main": sha(os.path.join(ROOT, "data", "manifest.json")),
            "sha_manifest_hr": sha(os.path.join(ROOT, "data", "hr", "manifest_hr.json")),
            "sha_manifest_sec": sha(os.path.join(ROOT, "data", "sec", "manifest_sec.json")),
            "sha_manifest_neu": sha(os.path.join(ROOT, "_daten-neu", "data", "neu", "manifest_neu.json")),
            "sha_manifest_energie": sha(os.path.join(ROOT, "_daten-energie", "data", "hr", "manifest_energie.json"))}

def laufeintrag(e):
    """Schreibt suche/laeufe/<Lauf-ID>.json und führt suche/letzter_lauf.json nach (lauf_id, stufen)."""
    e = {"lauf_id": LAUF_ID, "verfassung": VERFASSUNG, "beginn_utc": BEGINN.strftime("%Y-%m-%dT%H:%M:%SZ"),
         "ende_suche_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
         "anlass": os.environ.get("GITHUB_EVENT_NAME", "lokal"), "github_run_id": os.environ.get("GITHUB_RUN_ID"),
         "datenstand": datenstand(), **e}
    e.setdefault("stufen", {})
    for st in ("analyse", "familie_v", "einchecken"):
        e["stufen"].setdefault(st, "ausstehend")
    schreibe_json(e, os.path.join(LERNEN, "suche", "laeufe", f"{LAUF_ID}.json"))
    return e

def basis(pfad):
    return "file://" + os.path.join(ROOT, pfad, "data") if pfad else "file://" + os.path.join(ROOT, "data")

def grundname(indikator):
    for suf in ("_stand", "_d1", "_d5", "_d20", "_z252"):
        if indikator.endswith(suf):
            return indikator[:-len(suf)]
    return indikator

def exposition_nachfuehren(lernen, indikatoren, lauf_id, zeit_utc):
    """V3.12 (E31): Expositionsregister auf Ebene der Grundreihe – wann wurde eine Reihe erstmals gerechnet und
    veröffentlicht? «Vorbekannt» gilt für die ganze Verwandtschaft (gleiche Grundreihe, anderes Ziel, andere Variante,
    andere Haltedauer); darum genügt ein Eintrag je Grundreihe. Das Register ist eine Kennzeichnung, kein Ausschluss.
    Fehlt die Datei, wird sie einmalig aus den vorhandenen Vollarchiven suche/S####_alle.csv.gz aufgebaut; Reihen ohne
    Archivbeleg erhalten den aktuellen Lauf als früheste belegte Sicht. Bestehende Einträge werden nie geändert."""
    import csv, io, re
    pf = os.path.join(lernen, "exposition.json")
    try:
        reg_ = json.load(open(pf, encoding="utf-8"))
    except (OSError, ValueError):
        reg_ = {"regel": "E31: erste belegte Rechnung und Veröffentlichung je Grundreihe; Kennzeichnung, kein Ausschluss", "grundreihen": {}}
        sd = os.path.join(lernen, "suche")
        for name in sorted(x for x in os.listdir(sd) if re.fullmatch(r"S\d{4}_alle\.csv\.gz", x)):
            try:
                doc = json.load(open(os.path.join(sd, name[:5] + ".json"), encoding="utf-8"))
                rd = csv.DictReader(io.StringIO(gzip.decompress(open(os.path.join(sd, name), "rb").read()).decode("utf-8")))
                gesehen = {grundname(z["indikator"]) for z in rd}
            except Exception:
                continue
            for g in sorted(gesehen):
                reg_["grundreihen"].setdefault(g, {"erst_dokument": name[:5], "erst_lauf": doc.get("lauf_id"), "erst_zeit": doc.get("zeit"),
                                                   "beleg": f"suche/{name}"})
        reg_["aufbau"] = {"lauf_id": lauf_id, "zeit_utc": zeit_utc, "hinweis": "einmalig aus den vorhandenen Vollarchiven aufgebaut; frühere Läufe ohne Vollarchiv sind nicht belegt"}
    neu_ = 0
    for g in sorted({grundname(i) for i in indikatoren}):
        if g not in reg_["grundreihen"]:
            reg_["grundreihen"][g] = {"erst_dokument": None, "erst_lauf": lauf_id, "erst_zeit": zeit_utc, "beleg": f"suche/laeufe/{lauf_id}.json"}
            neu_ += 1
    reg_["grundreihen"] = dict(sorted(reg_["grundreihen"].items()))
    reg_["stand"] = {"lauf_id": lauf_id, "zeit_utc": zeit_utc, "grundreihen_n": len(reg_["grundreihen"])}
    schreibe_json(reg_, pf)
    return neu_, len(reg_["grundreihen"])

def index_abgleichen(index, lernen):
    """V3.12 (Schritt 2): Stimmt die Kandidatenzahl eines Indexeintrags nicht mit seinem S-Dokument überein, gilt das
    Dokument. Die Berichtigung wird in index["berichtigungen"] festgehalten (Anlass: S0022 wurde am 4.10.2026 von zwei
    Läufen vergeben; der Indexeintrag nannte die Zahl des Laufs, dessen Dokument als .konflikt_<zeit> daneben liegt)."""
    n = 0
    for e in index.get("suchlaeufe", []):
        d = e.get("datei")
        if not d:
            continue
        try:
            k = json.load(open(os.path.join(lernen, d), encoding="utf-8")).get("kandidaten")
        except (OSError, ValueError):
            continue
        if isinstance(k, int) and e.get("kandidaten") != k:
            index.setdefault("berichtigungen", []).append({"wo": f"suchlaeufe[nr={e.get('nr')}].kandidaten", "vorher": e.get("kandidaten"),
                                                            "jetzt": k, "grund": "Abgleich mit dem S-Dokument", "lauf_id": LAUF_ID})
            e["kandidaten"] = k; n += 1
    return n

# ---------------------------------------------------------------- Stand lesen
ip = os.path.join(LERNEN, "index.json")
if os.path.exists(ip):
    index = json.load(open(ip, encoding="utf-8"))
else:   # Startwerte wie im Auftrag der Lernrunde
    index = {"kumuliert": 59525, "lernberichte": [], "reihen_letzter_suchlauf": [],
             "suchlaeufe": [{"nr": n, "datei": None, "kandidaten": k, "in_db": True}
                            for n, k in [(1, 9332), (2, 13573), (3, 18317), (4, 18303)]]}
    print("index.json fehlt: Startwerte gesetzt")
_nb = index_abgleichen(index, LERNEN)
if _nb:
    print(f"Index: {_nb} Eintrag/Einträge mit dem S-Dokument abgeglichen (siehe index.json, Feld berichtigungen)")
reg = os.path.join(LERNEN, "hypothesen.txt.gz")
if not os.path.exists(reg):
    reg = os.path.join(ROOT, "hypothesen_start.txt.gz")

env = dict(os.environ, PS_CACHE=os.path.join(LAUF, "cache"), PS_KUM_VORHER=str(int(index["kumuliert"])),
           PS_REGISTER=reg, PS_PAARE=os.path.join(ROOT, "paare.txt"), PS_MECHANISMEN=os.path.join(ROOT, "mechanismen.txt"))
env.setdefault("PS_PLACEBO", "200")
# V3.18 (E9 Stufe 2, Entwurf): eingefrorener Discovery-Stand auf claude/lernen; nur die Suche nimmt neue Dateien auf.
STAND_DIR = os.path.join(LERNEN, "discovery")
for _k in [k for k in env if k.startswith("PS_DISCOVERY_")]:
    env.pop(_k)
if STAND_AKTIV:
    env.update(PS_DISCOVERY_STAND=STAND_DIR, PS_DISCOVERY_EINFRIEREN="1", PS_DISCOVERY_BERICHT="1",
               PS_DISCOVERY_NACHFUEHRUNG=os.path.join(ROOT, "nachfuehrung.json"), PS_LAUF_ID=LAUF_ID)
args = [sys.executable, os.path.join(ROOT, "suchmaschine.py"), basis(None)]
for pfad, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
    if os.path.isdir(os.path.join(ROOT, pfad, "data")):
        env[var] = basis(pfad)
    else:
        print(f"{pfad} fehlt: diese Reihen entfallen")
print("Aufruf:", " ".join(args), "| Energie", env.get("PS_BASIS_ENERGIE"), "| Scout", env.get("PS_BASIS_NEU"), "| kumuliert vorher", index["kumuliert"], "| Register", reg, flush=True)

CODE_DATEIEN = ("suchmaschine.py", "paare.txt", "suche_lauf.py", "mechanismen.txt", "korrekturen_neu.json", "explorativ.json", "eingabe.py",
                "discovery.py", "nachfuehrung.json")   # V3.18 E9 (Entwurf): Stand-Code und Nachführliste
code_hash = hashlib.sha256("".join(sha(os.path.join(ROOT, f)) or "" for f in CODE_DATEIEN).encode()).hexdigest()[:16]
letzter_s = next((s["datei"] for s in reversed(index["suchlaeufe"]) if s.get("datei")), None)


def ordner_sha(pfad):
    """Prüfsumme aller Dateien eines Ordners (Name und Inhalt), z. B. vorregistrierung/ auf main."""
    if not os.path.isdir(pfad):
        return None
    m = hashlib.sha256()
    for wurzel, _, dateien in sorted(os.walk(pfad)):
        for d in sorted(dateien):
            q = os.path.join(wurzel, d)
            m.update(os.path.relpath(q, pfad).encode("utf-8")); m.update((sha(q) or "").encode())
    return m.hexdigest()[:16]


def github_ausgabe(k, v):
    if os.environ.get("GITHUB_OUTPUT"):
        with open(os.environ["GITHUB_OUTPUT"], "a") as f:
            f.write(f"{k}={v}\n")


def register_sha(pfad):
    """V3.18 E9 (Entwurf): Prüfsumme des entpackten Registers, unabhängig von der Gzip-Fassung."""
    try:
        return hashlib.sha256(gzip.decompress(open(pfad, "rb").read())).hexdigest()[:16]
    except Exception:
        return None


def eingabe_gesamt():
    """V3.17 §4: Eingabe der Discovery (aus der Suchmaschine) plus Register, Code, Vorregistrierungen und Placebo-Zahl."""
    try:
        teil = json.load(open(os.path.join(LAUF, "eingabe.json"), encoding="utf-8"))
    except (OSError, ValueError):
        return None, None
    ganz = {"daten": teil.get("eingabe_hash"), "register": register_sha(reg), "code": code_hash,
            "vorregistrierung": ordner_sha(os.path.join(ROOT, "vorregistrierung")), "placebo": env.get("PS_PLACEBO")}
    return hashlib.sha256(json.dumps(ganz, sort_keys=True).encode()).hexdigest()[:16], dict(ganz, teile=teil.get("teile"))


def eingabe_nach_eintragung(kum_neu, reg_neu):
    """V3.18 (E9, Entwurf): Vergleichs-Prüfsumme nach der eigenen Registereintragung des Laufs, genau so, wie die Prüfung
    am Folgetag sie ohne weitere Änderung berechnet: neues Register und neue kumulierte Zahl, alles andere gleich."""
    try:
        teil = json.load(open(os.path.join(LAUF, "eingabe.json"), encoding="utf-8"))
        from eingabe import pruefsumme
    except (OSError, ValueError, ImportError):
        return None
    teile = dict(teil.get("teile") or {})
    if "KUM_VORHER" not in teile or kum_neu is None or not os.path.exists(reg_neu):
        return None
    if pruefsumme(teile) != teil.get("eingabe_hash"):   # Gutachten 23, M2: nur bei nachweislich gleicher Definition
        return None
    teile["KUM_VORHER"] = pruefsumme(int(kum_neu))
    ganz = {"daten": pruefsumme(teile), "register": register_sha(reg_neu), "code": code_hash,
            "vorregistrierung": ordner_sha(os.path.join(ROOT, "vorregistrierung")), "placebo": env.get("PS_PLACEBO")}
    return hashlib.sha256(json.dumps(ganz, sort_keys=True).encode()).hexdigest()[:16]


# ---------------------------------------------------------------- V3.18 (E9 Stufe 2, Entwurf): Eingabe-Durchgang
# Vor jeder Rechnung (auch bei Push): Dateien aus dem eingefrorenen Stand bereitstellen, neue Dateien einfrieren,
# freigegebene Nachführungen anwenden, Revisionen des Spiegels berichten, Eingabe-Prüfsumme schreiben.
_p0 = subprocess.run(args, cwd=LAUF, env=dict(env, PS_NUR_EINGABEHASH="1"), capture_output=True, text=True)
rc0 = _p0.returncode
try:
    _sb = json.load(open(os.path.join(LAUF, "discovery_bericht.json"), encoding="utf-8"))
except (OSError, ValueError):
    _sb = None
_gelesen = set(_sb["gelesen"]) if (_sb and isinstance(_sb.get("gelesen"), list)) else None   # ohne Bericht: alles streng
_pr = (discovery.pruefen(STAND_DIR, _gelesen) if STAND_AKTIV else
       {"dateien_n": 0, "verstoesse": [], "befunde_nicht_gelesen": [], "ohne_eintrag": []})
# Gutachten 23, M1/M2: Eingabe der Vorprüfung (soll gerechnet werden), die festgehaltene Fassung von stand.json und die
# von der Vorprüfung bereitgestellten Dateien (Cache der Suchmaschine). Die Rechnung liest ausschliesslich diese Dateien.
eg_vor, eg_vor_teile = eingabe_gesamt() if rc0 == 0 else (None, None)
STAND_FASSUNG = sha(os.path.join(STAND_DIR, "stand.json")) if STAND_AKTIV else None


def bereitgestellt():
    c = env["PS_CACHE"]
    try:
        namen = sorted(os.listdir(c))
    except OSError:
        return {}
    return {n: sha(os.path.join(c, n)) for n in namen if os.path.isfile(os.path.join(c, n))}


CACHE_VOR = bereitgestellt()
if _sb is not None:
    schreibe_json({"lauf_id": LAUF_ID, "zeit_utc": BEGINN.strftime("%Y-%m-%dT%H:%M:%SZ"), "regel": _sb.get("regel"),
                   "revisionen_n": _sb.get("revisionen_n"), "revisionen_je_gruppe": _sb.get("revisionen_je_gruppe"),
                   "revisionen_summe": _sb.get("revisionen_summe"), "revisionen": _sb.get("revisionen")},
                  os.path.join(STAND_DIR, "revisionen.json"))
STAND_KURZ = {
    "aktiv": STAND_AKTIV, "ordner": "discovery/ (claude/lernen)", "dateien_n": _pr["dateien_n"],
    "fassung": STAND_FASSUNG, "fassung_regel": "Prüfsumme von stand.json nach der Vorprüfung; die Rechnung liest nur die daraus bereitgestellten Dateien (Gutachten 23, M1)",
    "bereitgestellt": {"dateien_n": len(CACHE_VOR), "pruefsumme": hashlib.sha256(json.dumps(CACHE_VOR, sort_keys=True).encode()).hexdigest()[:16]},
    "neu_eingefroren_n": (_sb or {}).get("neu_eingefroren_n"), "neu_eingefroren": ((_sb or {}).get("neu_eingefroren") or [])[:60],
    "nachgefuehrt": (_sb or {}).get("nachgefuehrt"), "nachfuehrung_angewandt": (_sb or {}).get("nachfuehrung_angewandt"),
    "nachfuehrung_fehler": (_sb or {}).get("nachfuehrung_fehler"), "nicht_eingefroren": (_sb or {}).get("nicht_eingefroren"),
    "revisionen_n": (_sb or {}).get("revisionen_n"), "revisionen_je_gruppe": (_sb or {}).get("revisionen_je_gruppe"),
    "revisionen_summe": (_sb or {}).get("revisionen_summe"),
    "revisionen_bericht": "discovery/revisionen.json (nur Bericht, löst nichts aus)",
    "einfrierpruefung": {"bestanden": not _pr["verstoesse"], "verstoesse": _pr["verstoesse"][:20],
                         "befunde_nicht_gelesen": _pr.get("befunde_nicht_gelesen", [])[:20],
                         "geprueft": ("alle gelesenen eingefrorenen Fassungen streng" if _gelesen is not None
                                      else "alle eingefrorenen Fassungen streng (kein Bericht)"),
                         "nicht_eingefroren": "nicht im Stand; Stichtagskürzung der Suchmaschine wie bisher",
                         "ohne_eintrag_n": len(_pr["ohne_eintrag"])},
}
if rc0 != 0:
    STAND_KURZ["eingabe_durchgang_fehler"] = (_p0.stdout + _p0.stderr)[-1500:]


def abbruch(fehler, status, hinweis, e9):
    """Gutachten 23, M1: Der Lauf endet vor oder nach der Rechnung ohne Ergebnis; er ist fehlgeschlagen und wird nicht
    Vergleichsstand (lauf_status.py setzt nur importierbare Läufe als Referenz)."""
    laufeintrag({"stufen": {"suche": "fehlgeschlagen"}, "e9": e9, "fehler": fehler, "ausgaben": None, "hinweis": hinweis})
    _lp = os.path.join(LERNEN, "suche", "letzter_lauf.json")
    try:
        _alt = json.load(open(_lp, encoding="utf-8"))
    except (OSError, ValueError):
        _alt = {}
    _alt["letzter_versuch"] = {"lauf_id": LAUF_ID, "status": status, "zeit_utc": BEGINN.strftime("%Y-%m-%dT%H:%MZ")}
    schreibe_json(_alt, _lp)
    print(f"Lauf {LAUF_ID}: {fehler}"); sys.exit(4)


if _pr["verstoesse"]:
    abbruch(f"Einfrierprüfung nicht bestanden: {len(_pr['verstoesse'])} Verstoss/Verstösse im Discovery-Stand; nicht gerechnet",
            "fehlgeschlagen (Einfrierprüfung)",
            ("Kein Ergebnis dieses Laufs. Behebung über einen freigegebenen Eintrag in nachfuehrung.json für die genannten "
             "Dateien (ersetzt auch eine fehlende oder beschädigte Fassung) oder Rückweg mit discovery.AKTIV = False."),
            {"modus": "V3.18: Einfrierprüfung vor der Rechnung", "stand": STAND_KURZ})
if STAND_AKTIV and (eg_vor is None or _sb is None):   # Gutachten 23, M1: unlesbare Pflicht-Eingabe -> Abbruch, kein Ersatz
    abbruch("Vorprüfung fehlgeschlagen: Eingabe nicht vollständig lesbar, Eingabe-Prüfsumme oder Bericht des Stands fehlt; nicht gerechnet",
            "fehlgeschlagen (Vorprüfung)",
            ("Kein Ergebnis dieses Laufs (V3.18 §3 Ziff. 9 und §5). Ursache siehe e9.stand.eingabe_durchgang_fehler. "
             "Die Daten werden nicht ersetzt; der nächste Lauf versucht es erneut."),
            {"modus": "V3.18: Vorprüfung vor der Rechnung", "stand": STAND_KURZ})
_l_gelesen = any(n.startswith("french__") and "aily" in n for n in (_gelesen or ()))
if STAND_AKTIV and os.environ.get("PS_LANGZEIT", "1") == "1" and ("Langzeit übersprungen" in (_p0.stdout or "") or not _l_gelesen):
    # Familie L ist Pflichtbestand (Gutachten 23, M1): nicht gelesen oder nicht aufgebaut -> Abbruch
    abbruch("Vorprüfung fehlgeschlagen: Familie L (Ken French) nicht lesbar; nicht gerechnet",
            "fehlgeschlagen (Vorprüfung)",
            ("Kein Ergebnis dieses Laufs (V3.18 §3 Ziff. 9). Familie L wird nicht stillschweigend weggelassen. "
             "Behebung über Nachführung oder Rückweg (§8)."),
            {"modus": "V3.18: Vorprüfung vor der Rechnung", "stand": STAND_KURZ})

E9 = {"modus": "immer (Push oder manuell)", "eingabe_hash": eg_vor, "stand": STAND_KURZ}
if os.environ.get("PS_E9") == "1":
    eg, eg_teile = eg_vor, eg_vor_teile
    ref = index.get("letzter_eingabe_hash")
    wtag = int(os.environ.get("PS_E9_WOCHENTAG_TEST", BEGINN.astimezone(ZoneInfo("Europe/Zurich")).weekday()))   # Variable nur für Tests
    montag = wtag == 0
    anlaesse = []
    if eg is None:
        anlaesse.append("Eingabe nicht lesbar")
    elif ref is None:
        anlaesse.append("kein gültiger Referenzlauf")
    elif eg != ref:
        anlaesse.append("Eingaben geändert")
    if montag:
        anlaesse.append("Kontrolllauf (Montag)")
    E9 = {"modus": "bei Änderung (V3.17, E9; V3.18 mit eingefrorenem Stand, Entwurf)", "eingabe_hash": eg, "referenz_eingabe_hash": ref,
          "referenz_lauf": index.get("letzter_gueltiger_lauf"), "anlaesse": anlaesse, "eingabe": eg_teile, "stand": STAND_KURZ}
    if not anlaesse:
        laufeintrag({"stufen": {"suche": "keine Neuberechnung"}, "e9": E9,
                     "ausgaben": {"s_dokument": letzter_s, "vollarchiv": index.get("letztes_vollarchiv"),
                                  "art": "keine Neuberechnung: Eingaben unverändert gegenüber dem letzten gültigen Lauf; kein neues Ergebnis, kein neuer Befund"}})
        github_ausgabe("gerechnet", "false")
        print(f"Lauf {LAUF_ID}: keine Neuberechnung (Eingabe {eg} = Referenz, kein Montag)."); sys.exit(0)
    print("V3.17 E9: gerechnet wird –", ", ".join(anlaesse))
github_ausgabe("gerechnet", "true")

logp = os.path.join(LAUF, "log.txt")
env_rechnung = dict(env)
if STAND_AKTIV:   # Gutachten 23, M1: Die Rechnung liest nur die festgehaltene Fassung (kein Einfrieren, keine Nachführung)
    env_rechnung.update(PS_DISCOVERY_EINFRIEREN="0", PS_DISCOVERY_BERICHT="0")
    env_rechnung.pop("PS_DISCOVERY_NACHFUEHRUNG", None)
with open(logp, "w") as lg:
    rc = subprocess.run(args, cwd=LAUF, env=env_rechnung, stdout=lg, stderr=subprocess.STDOUT).returncode
log = open(logp, encoding="utf-8", errors="replace").read()
print(log[-6000:])
if rc != 0:
    print(f"Suchmaschine mit Fehler {rc} beendet")
    laufeintrag({"stufen": {"suche": "fehlgeschlagen"}, "fehler": f"Suchmaschine mit Fehler {rc} beendet", "log_ende": log[-3000:],
                 "ausgaben": None, "hinweis": "Kein Ergebnis dieses Laufs; letzter_lauf.json und S-Dokumente zeigen frühere Läufe."})
    lp = os.path.join(LERNEN, "suche", "letzter_lauf.json")
    try:
        alt = json.load(open(lp, encoding="utf-8"))
    except (OSError, ValueError):
        alt = {}
    alt["letzter_versuch"] = {"lauf_id": LAUF_ID, "status": "fehlgeschlagen", "zeit_utc": BEGINN.strftime("%Y-%m-%dT%H:%MZ")}
    schreibe_json(alt, lp)
    sys.exit(rc)

zus = json.load(open(os.path.join(LAUF, "suchlauf_zusammenfassung.json")))
eg_rechnung, _ = eingabe_gesamt()   # Eingabe-Prüfsumme, wie die Rechnung sie gebildet hat
eg_lauf = eg_vor if eg_vor is not None else eg_rechnung   # tatsächliche Eingabe, vor der Rechnung gesichert (Gutachten 23, M2)
if STAND_AKTIV:   # Gutachten 23, M1: Die Rechnung las genau die von der Vorprüfung bereitgestellten Dateien
    _fest = []
    if sha(os.path.join(STAND_DIR, "stand.json")) != STAND_FASSUNG:
        _fest.append("stand.json hat sich während der Rechnung geändert")
    if eg_rechnung != eg_vor:
        _fest.append(f"Eingabe-Prüfsumme der Rechnung {eg_rechnung} ungleich Vorprüfung {eg_vor}")
    CACHE_NACH = bereitgestellt()
    _anders = sorted(n for n in CACHE_VOR if CACHE_NACH.get(n) != CACHE_VOR[n])
    _dazu = sorted(set(CACHE_NACH) - set(CACHE_VOR))
    if _anders:
        _fest.append(f"bereitgestellte Dateien während der Rechnung verändert: {_anders[:5]}")
    if _dazu:
        _fest.append(f"Dateien gelesen, welche die Vorprüfung nicht bereitgestellt hat: {_dazu[:5]}")
    STAND_KURZ["rechnung_auf_fassung"] = "bestätigt: gleiche Fassung, gleiche bereitgestellte Dateien, gleiche Eingabe" if not _fest else _fest
    if _fest:
        abbruch("Rechnung nicht auf der vorgeprüften Fassung: " + "; ".join(_fest), "fehlgeschlagen (Fassung)",
                "Kein Ergebnis dieses Laufs (V3.18 §3 Ziff. 3, Gutachten 23 M1). Die Ausgaben der Rechnung werden nicht verwendet.",
                dict(E9, eingabe_hash_vorpruefung=eg_vor, eingabe_hash_lauf=eg_lauf, eingabe_hash_rechnung=eg_rechnung))

herkunft = {
    "commit_main": commit(ROOT), "commit_energie": commit(os.path.join(ROOT, "_daten-energie")),
    "commit_neu": commit(os.path.join(ROOT, "_daten-neu")), "commit_lernen_vorher": commit(LERNEN),
    "code_hash": code_hash, "sha_suchmaschine": sha(os.path.join(ROOT, "suchmaschine.py")),
    "sha_paare": sha(os.path.join(ROOT, "paare.txt")), "sha_mechanismen": sha(os.path.join(ROOT, "mechanismen.txt")), "sha_register_vorher": sha(reg),
    "sha_manifest_main": sha(os.path.join(ROOT, "data", "manifest.json")),
    "sha_manifest_neu": sha(os.path.join(ROOT, "_daten-neu", "data", "neu", "manifest_neu.json")),
    "placebo_laeufe": zus.get("placebo_laeufe"), "umgebung": zus.get("umgebung"),
}
jetzt = datetime.now(timezone.utc)
def ergebnis_pruefsumme(pfad):
    """Prüfsumme aller Ergebnisse eines Laufs, ohne die Spalte «neu» (die nur sagt, ob der Schlüssel schon im Register stand)."""
    import csv, io
    try:
        zeilen = csv.reader(io.StringIO(gzip.decompress(open(pfad, "rb").read()).decode("utf-8")))
        kopf = next(zeilen); weg = kopf.index("neu") if "neu" in kopf else None
        m = hashlib.sha256()
        for z in [kopf] + list(zeilen):
            if weg is not None:
                z = z[:weg] + z[weg + 1:]
            m.update(("\x1f".join(z) + "\n").encode("utf-8"))
        return m.hexdigest()[:16]
    except Exception:
        return None

ergebnis_hash = ergebnis_pruefsumme(os.path.join(LAUF, "suchlauf_echt.csv.gz"))
code_neu = index.get("letzter_code_hash") != code_hash
ergebnis_neu = ergebnis_hash is None or index.get("letzter_ergebnis_hash") != ergebnis_hash
vollarchiv = bool(zus["kandidaten_neu"] > 0 or code_neu or ergebnis_neu)   # V3.17 (E38): Archiv passt immer zum Ergebnis
vorher = list(index.get("reihen_letzter_suchlauf") or [])
entfallen = sorted(set(vorher) - set(zus["indikatoren"])); neu_dabei = sorted(set(zus["indikatoren"]) - set(vorher))
kern = {"kandidaten": zus["kandidaten"], "kandidaten_neu": zus["kandidaten_neu"], "huerde_t": zus["huerde_t"],
        "echt_bestes_t": zus.get("echt_bestes_t"), "p_lauf": zus.get("p_lauf"),
        "kandidaten_stufe_d": len(zus["bausteine"]), "fehlalarmrate": zus.get("fehlalarmrate"), "placebo_laeufe": zus.get("placebo_laeufe")}
s_schreiben = bool(vollarchiv or ergebnis_neu)
nr = max([s["nr"] for s in index["suchlaeufe"]] + [0]) + 1
# V3.18 E9 (Entwurf): Register und kumulierte Zahl so, wie sie nach diesem Lauf auf claude/lernen stehen. Nur die eigenen
# Änderungen dieses Laufs sind eingerechnet; was andere während des Laufs auf claude/lernen eintragen, bleibt eine
# offene Änderung und löst den nächsten Lauf aus (Gutachten 23, M2).
eg_nach = (eingabe_nach_eintragung(zus.get("kandidaten_kumuliert"), os.path.join(LAUF, "hypothesen.txt.gz")) if s_schreiben
           else eingabe_nach_eintragung(index.get("kumuliert"), reg))
# Gutachten 23 (M2/M3): Entscheidungs-Prüfsumme über die Positivliste eingabe.ENTSCHEIDUNG_FELDER (Placebo-Pfad, Hürden,
# Route C, Kandidaten der Stufe D, Kalibrierung); ohne Zähler, Kennzeichen «neu», Bonferroni-Bericht und ohne die Berichte
# aus den täglichen Manifesten.
entscheidung_hash = entscheidung_pruefsumme(zus)
wiederholbarkeit, wiederholbarkeit_detail = None, None
if E9.get("anlaesse") == ["Kontrolllauf (Montag)"]:
    _g_erg = ergebnis_hash == index.get("letzter_ergebnis_hash")
    _ref_ent = index.get("letzter_entscheidung_hash")
    _g_ent = None if _ref_ent is None else entscheidung_hash == _ref_ent
    wiederholbarkeit = ("gleich" if _g_erg and _g_ent is not False else
                        "Abweichung trotz gleicher Eingaben – zu klären; keine neue Evidenz (V3.17 §4)")
    wiederholbarkeit_detail = {"ergebnis": "gleich" if _g_erg else "abweichend",
                               "entscheidungen": ("kein Vergleichswert (erster Lauf mit Entscheidungs-Prüfsumme)" if _g_ent is None
                                                  else "gleich" if _g_ent else "abweichend"),
                               "startwerte": "fest im Code (Placebo 1000+s, Auswahl 20260925, F5 5000+s, Kalibrierung 777)"}
index["letzter_entscheidung_hash"] = entscheidung_hash
eintrag = laufeintrag({
    "stufen": {"suche": "vollständig"}, "herkunft": herkunft, "ergebnis_hash": ergebnis_hash, **kern,
    "reihen": {"vorhanden_n": len(zus["indikatoren"]), "vorlauf_n": len(vorher), "entfallen_gegen_vorlauf": entfallen,
               "neu_gegen_vorlauf": neu_dabei, "erwartet_und_gesperrt": zus.get("reihen_bericht"),
               "liste": "index.json Feld reihen_letzter_suchlauf"},
    "ausgaben": {"s_dokument": f"suche/S{nr:04d}.json" if s_schreiben else letzter_s,
                 "s_dokument_art": "neu in diesem Lauf" if s_schreiben else "unverändert: Ergebnisse dieses Laufs sind Zeichen für Zeichen gleich wie im genannten Dokument",
                 "vollarchiv": f"suche/S{nr:04d}_alle.csv.gz" if vollarchiv else index.get("letztes_vollarchiv"),
                 "vollarchiv_art": "neu in diesem Lauf" if vollarchiv else "aus einem früheren Lauf mit Zeichen für Zeichen gleichen Ergebnissen",
                 "vollarchiv_ergebnis_hash": ergebnis_hash if vollarchiv else index.get("letztes_vollarchiv_ergebnis_hash")},
    "e9": dict(E9, eingabe_hash_vorpruefung=eg_vor, eingabe_hash_lauf=eg_lauf, eingabe_hash_rechnung=eg_rechnung,
               eingabe_hash_nach_eintragung=eg_nach,
               bedeutung={"eingabe_hash_lauf": "tatsächliche Eingabe dieser Rechnung, in der Vorprüfung vor der Rechnung gesichert; massgeblich für E38 und Finalisten",
                          "eingabe_hash_nach_eintragung": "nur Vergleichsstand für den Auslöser (§4): Ausgangszustand plus eigene Register- und Zählstandsänderungen; nicht für E38 oder Finalisten"}),
    "entscheidung_hash": entscheidung_hash, "wiederholbarkeit": wiederholbarkeit, "wiederholbarkeit_detail": wiederholbarkeit_detail,
    "anlass_s": ("neue Hypothesen" if zus["kandidaten_neu"] > 0 else "geänderter Code" if code_neu else
                 "geänderte Ergebnisse (Datenstand)" if ergebnis_neu else "keiner"),
})
schreibe_json({"zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ"), "lauf_id": LAUF_ID, "verfassung": VERFASSUNG, **herkunft, "ergebnis_hash": ergebnis_hash,
           "kandidaten": zus["kandidaten"], "kandidaten_neu": zus["kandidaten_neu"], "huerde_t": zus["huerde_t"],
           "fund": False,   # V3.11 (E26): die Discovery wählt nur aus; ein Fund entsteht erst in Stufe B
           "kandidaten_stufe_d": len(zus["bausteine"]), "p_lauf": zus.get("p_lauf"), "bausteine": len(zus["bausteine"]),
           "stufen": eintrag["stufen"], "laufeintrag": f"suche/laeufe/{LAUF_ID}.json",
           "reihen_entfallen_gegen_vorlauf": entfallen, "reihen_neu_gegen_vorlauf": neu_dabei},
          os.path.join(LERNEN, "suche", "letzter_lauf.json"))
index.setdefault("laeufe", []).append({"datei": f"suche/laeufe/{LAUF_ID}.json", "lauf_id": LAUF_ID,
                                         "s_dokument": eintrag["ausgaben"]["s_dokument"], "ergebnis_hash": ergebnis_hash})
index["reihen_letzter_suchlauf"] = zus["indikatoren"]
_en, _eg = exposition_nachfuehren(LERNEN, zus["indikatoren"], LAUF_ID, jetzt.strftime("%Y-%m-%dT%H:%MZ"))
index["exposition"] = {"datei": "exposition.json", "grundreihen_n": _eg, "neu_in_diesem_lauf": _en}
index["letzter_lauf_utc"] = jetzt.strftime("%Y-%m-%dT%H:%MZ")
if not s_schreiben:
    schreibe_json(index, ip)
    print(f"Lauf {LAUF_ID}: keine neuen Hypothesen, Code und Ergebnisse unverändert. Laufeintrag geschrieben, kein neues S-Dokument "
          f"(gilt weiter: {letzter_s})."); sys.exit(0)

# ---------------------------------------------------------------- Ergebnis ablegen
lokal = jetzt.astimezone(ZoneInfo("Europe/Zurich"))

def fmt(r):
    return (f"{r['indikator']} {r['art']} -> {r['ziel']} {r['h']} Tage: t {r['t']:.2f}, n {r['n']}, "
            f"{r['mu']:.2f} pp je Wechsel gegenüber ACWI brutto, Hälften t {r['t1']:.2f} und {r['t2']:.2f}")

gruppen = {}
for i in zus["indikatoren"]:
    g = ("Scout" if i.startswith("neu_") else "SEC" if i.startswith("sec_") else "Paare" if i.startswith("paar_")
         else "Wetter" if i.startswith("wetter_") else "Strom" if i.startswith("strom_") else "Wikipedia" if i.startswith("wiki_")
         else "Bitcoin" if i.startswith("btc_") else "Indizes" if i.startswith("idx_") else "FRED")
    gruppen[g] = gruppen.get(g, 0) + 1
fund = False   # V3.11 (E26): ein Fund entsteht erst in Stufe B (Bestätigung der Finalisten)
ueber_placebo = bool(zus.get("fund"))   # bisheriges Kriterium (Kandidaten vorhanden und p_lauf höchstens 0.05): jetzt Diagnose
urteil = ("KANDIDAT(EN) DER STUFE D über den Placebo-Läufen – kein Fund; Bestätigung nur über die Finalistenfamilie (E27). "
          "Siegel nicht geöffnet." if ueber_placebo else
          "Kein Kandidat der Stufe D über den Placebo-Läufen. Validierung ab 2021 nicht angerührt (S4).")
if zus["bausteine"]:
    urteil += " Kandidaten: " + "; ".join(f"Route {b.get('route', 'A')}: {b['indikator']} {b['art']} -> {b['ziel']} {b['h']} Tage"
                                       for b in zus["bausteine"]) + "."
if zus["bausteine"] and not ueber_placebo:
    urteil += (f" {len(zus['bausteine'])} Kandidat(en), aber p_lauf {zus.get('p_lauf')} > 0.05 "
               "(Placebo-Läufe erreichen ebenso viele): Zufall nicht ausgeschlossen.")
if zus["langzeit_hinweise"]:
    urteil += f" {len(zus['langzeit_hinweise'])} Langzeit-Hinweis(e) ohne Bestätigung auf dem ETF (kein Baustein)."

S = {
    "nr": nr, "sort": nr,
    "zeit": lokal.strftime("%-d.%-m.%Y, %H:%M (Europe/Zurich)"),
    "verfassung": VERFASSUNG, "lauf_id": LAUF_ID, "stufe": "D (Discovery): Auswahl, kein Fund (V3.11, E26)",
    "ergebnis_hash": ergebnis_hash, "anlass": eintrag["anlass_s"],
    "reihen_entfallen_gegen_vorlauf": entfallen, "reihen_neu_gegen_vorlauf": neu_dabei,
    "methode": zus.get("methode", "M4"),
    "entstehung": "GitHub Action «Prüfstand Suche» (V3.4 E9)" + ("" if zus["kandidaten_neu"] else f", Anlass: {eintrag['anlass_s']}"),
    "herkunft": herkunft,
    "stichtag": "2020-12-31",
    "horizonte_tage": [1, 5, 20],
    "kandidaten": zus["kandidaten"], "kandidaten_neu": zus["kandidaten_neu"], "kandidaten_bekannt": zus["kandidaten_bekannt"],
    "kandidaten_kumuliert": zus["kandidaten_kumuliert"], "huerde_t": zus["huerde_t"],
    "huerde_art": zus.get("huerde_art"), "huerde_bonferroni_bericht": zus.get("huerde_bonferroni_bericht"),
    "huerde_c_t2": zus.get("huerde_c_t2"), "route_c_auswahl_k": zus.get("route_c_auswahl_k"),
    "route_c_stufe1": zus.get("route_c_stufe1"),
    "kosten_pp_je_wechsel": zus.get("kosten_pp_je_wechsel"), "kosten_teile": zus.get("kosten_teile"),
    "indizes": zus.get("indizes"), "staerkste_indizes": zus.get("staerkste_indizes"),
    "echt_bestes_t": zus.get("echt_bestes_t"), "placebo_bestes_t_je_lauf": zus.get("placebo_bestes_t_je_lauf"),
    # V3.12 (E27b, E30): ungerundete Placebo-Maxima (alle Kandidaten und nur bestätigungsfähige) als Grundlage des Rang-Scores
    "placebo_bestes_t_je_lauf_roh": zus.get("placebo_bestes_t_je_lauf_roh"),
    "placebo_bestes_t_bestaetigungsfaehig_je_lauf_roh": zus.get("placebo_bestes_t_bestaetigungsfaehig_je_lauf_roh"),
    "score_e27_regel": zus.get("score_e27_regel"),
    "explorativ_reihen_n": len((zus.get("reihen_bericht") or {}).get("explorativ_reihen") or []),
    "familien": zus["familien"],
    "indikatoren_n": zus["indikatoren_n"],
    "ziele_n": sum(len(v) for v in zus["ziele"].values()),
    "ziele": zus["ziele"],
    "indikatoren_quellen": ", ".join(f"{g} {n}" for g, n in sorted(gruppen.items())) + f"; Paare nach paare.txt: {zus['paare']}",
    "ergebnis_alle_filter": zus["echt_alle_filter_positiv"],
    "ergebnis_vorstufe_t35": zus["echt_vorstufe_positiv"],
    "placebo_laeufe": zus.get("placebo_laeufe"), "placebo_art": zus.get("placebo_art"), "fehlalarmrate": zus.get("fehlalarmrate"), "kalibrierung": zus.get("kalibrierung"), "familie_l_ereignisse": zus.get("familie_l_ereignisse"), "umgebung": zus.get("umgebung"),
    "placebo_bausteine_je_lauf": zus.get("placebo_bausteine_je_lauf"),
    "p_lauf": zus.get("p_lauf"),
    "fund": fund, "ueber_placebo_diagnose": ueber_placebo, "kandidaten_stufe_d": len(zus["bausteine"]),
    "datenpruefung_verdachtstage": zus.get("datenpruefung_verdachtstage"),
    "placebo_suchlaeufe_alle_filter": zus.get("placebo_alle_filter_je_lauf"),
    "placebo_suchlaeufe_vorstufe": zus.get("placebo_vorstufe_je_lauf"),
    "echt_mehr_als_staerkster_placebo": zus["echt_mehr_als_staerkster_placebo"],
    "bausteine": zus["bausteine"],
    "langzeit_hinweise": zus["langzeit_hinweise"],
    "staerkste_neue": "; ".join(fmt(r) for r in zus.get("staerkste_neue", [])[:3]) or "keine neuen Hypothesen",
    "staerkste_positive": zus["staerkste_positive"],
    "je_quelle": zus.get("je_quelle", {}),
    "urteil": urteil,
    "dauer_min": zus.get("dauer_min"),
}
name = f"S{nr:04d}"
schreibe_json(S, os.path.join(LERNEN, "suche", f"{name}.json"))
shutil.copy(os.path.join(LAUF, "hypothesen.txt.gz"), os.path.join(LERNEN, "hypothesen.txt.gz"))
ue = open(os.path.join(LAUF, "suchlauf_ueberlebende.csv"), encoding="utf-8").read().splitlines()
open(os.path.join(LERNEN, "suche", f"{name}_ueberlebende.csv"), "w", encoding="utf-8").write("\n".join(ue[:201]) + "\n")
open(os.path.join(LERNEN, "suche", f"{name}_log.txt"), "w", encoding="utf-8").write(log[-20000:])
if vollarchiv:
    shutil.copy(os.path.join(LAUF, "suchlauf_echt.csv.gz"), os.path.join(LERNEN, "suche", f"{name}_alle.csv.gz"))   # vollständige Ergebnisse
    index["letztes_vollarchiv"] = f"suche/{name}_alle.csv.gz"
    index["letztes_vollarchiv_ergebnis_hash"] = ergebnis_hash

index["kumuliert"] = zus["kandidaten_kumuliert"]
index["suchlaeufe"].append({"nr": nr, "datei": f"suche/{name}.json", "kandidaten": zus["kandidaten"], "in_db": False})
index["letzter_ergebnis_hash"] = ergebnis_hash
index["letzter_suchlauf_utc"] = jetzt.strftime("%Y-%m-%dT%H:%MZ")
index["letzter_code_hash"] = code_hash
index["methode"] = zus.get("methode", "M4")
schreibe_json(index, ip)
print(f"{name}: {zus['kandidaten']} Kandidaten, {zus['kandidaten_neu']} neu, kumuliert {zus['kandidaten_kumuliert']}, "
      f"Hürde {zus['huerde_t']}, Urteil: {urteil}")
