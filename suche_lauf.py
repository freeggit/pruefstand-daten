#!/usr/bin/env python3
"""Prüfstand – Suchlauf in der GitHub Action (Verfassung V3.6, Methode M2).

Liest den Stand auf dem Zweig claude/lernen (Arbeitskopie _lernen), rechnet die Suchmaschine auf den lokalen
Kopien von main, claude/daten-energie und claude/daten-neu und legt das Ergebnis auf claude/lernen ab:
  suche/S####.json (Format wie bisher, plus Felder V3.4), suche/S####_ueberlebende.csv, suche/S####_log.txt,
  hypothesen.txt.gz (Register V3.3), index.json (kumuliert, suchlaeufe, reihen_letzter_suchlauf).
Ein S####-Eintrag entsteht bei neuen Hypothesen ODER geändertem Code (Suchmaschine, paare.txt). Jeder Lauf schreibt
zusätzlich suche/letzter_lauf.json mit Commit-IDs aller Zweige und Prüfsummen (Nachvollziehbarkeit, V3.6).
Die Routine «Prüfstand Lernrunde» rechnet nicht mehr selbst; sie liest diese Dateien und schreibt den Lernbericht.
"""
import hashlib, json, os, shutil, subprocess, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.path.join(ROOT, "_lernen")
LAUF = os.environ.get("PS_LAUF", "/tmp/lauf")
os.makedirs(LAUF, exist_ok=True)
os.makedirs(os.path.join(LERNEN, "suche"), exist_ok=True)

def basis(pfad):
    return "file://" + os.path.join(ROOT, pfad, "data") if pfad else "file://" + os.path.join(ROOT, "data")

# ---------------------------------------------------------------- Stand lesen
ip = os.path.join(LERNEN, "index.json")
if os.path.exists(ip):
    index = json.load(open(ip, encoding="utf-8"))
else:   # Startwerte wie im Auftrag der Lernrunde
    index = {"kumuliert": 59525, "lernberichte": [], "reihen_letzter_suchlauf": [],
             "suchlaeufe": [{"nr": n, "datei": None, "kandidaten": k, "in_db": True}
                            for n, k in [(1, 9332), (2, 13573), (3, 18317), (4, 18303)]]}
    print("index.json fehlt: Startwerte gesetzt")
reg = os.path.join(LERNEN, "hypothesen.txt.gz")
if not os.path.exists(reg):
    reg = os.path.join(ROOT, "hypothesen_start.txt.gz")

env = dict(os.environ, PS_CACHE=os.path.join(LAUF, "cache"), PS_KUM_VORHER=str(int(index["kumuliert"])),
           PS_REGISTER=reg, PS_PAARE=os.path.join(ROOT, "paare.txt"))
env.setdefault("PS_PLACEBO", "100")
args = [sys.executable, os.path.join(ROOT, "suchmaschine.py"), basis(None)]
for pfad, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
    if os.path.isdir(os.path.join(ROOT, pfad, "data")):
        env[var] = basis(pfad)
    else:
        print(f"{pfad} fehlt: diese Reihen entfallen")
print("Aufruf:", " ".join(args), "| Energie", env.get("PS_BASIS_ENERGIE"), "| Scout", env.get("PS_BASIS_NEU"), "| kumuliert vorher", index["kumuliert"], "| Register", reg, flush=True)

logp = os.path.join(LAUF, "log.txt")
with open(logp, "w") as lg:
    rc = subprocess.run(args, cwd=LAUF, env=env, stdout=lg, stderr=subprocess.STDOUT).returncode
log = open(logp, encoding="utf-8", errors="replace").read()
print(log[-6000:])
if rc != 0:
    print(f"Suchmaschine mit Fehler {rc} beendet"); sys.exit(rc)

zus = json.load(open(os.path.join(LAUF, "suchlauf_zusammenfassung.json")))

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

code_hash = hashlib.sha256("".join(sha(os.path.join(ROOT, f)) or "" for f in ("suchmaschine.py", "paare.txt", "suche_lauf.py")).encode()).hexdigest()[:16]
herkunft = {
    "commit_main": commit(ROOT), "commit_energie": commit(os.path.join(ROOT, "_daten-energie")),
    "commit_neu": commit(os.path.join(ROOT, "_daten-neu")), "commit_lernen_vorher": commit(LERNEN),
    "code_hash": code_hash, "sha_suchmaschine": sha(os.path.join(ROOT, "suchmaschine.py")),
    "sha_paare": sha(os.path.join(ROOT, "paare.txt")), "sha_register_vorher": sha(reg),
    "sha_manifest_main": sha(os.path.join(ROOT, "data", "manifest.json")),
    "sha_manifest_neu": sha(os.path.join(ROOT, "_daten-neu", "data", "neu", "manifest_neu.json")),
    "placebo_laeufe": zus.get("placebo_laeufe"),
}
jetzt = datetime.now(timezone.utc)
json.dump({"zeit_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ"), **herkunft, "kandidaten": zus["kandidaten"],
           "kandidaten_neu": zus["kandidaten_neu"], "huerde_t": zus["huerde_t"], "fund": zus.get("fund"),
           "p_lauf": zus.get("p_lauf"), "bausteine": len(zus["bausteine"])},
          open(os.path.join(LERNEN, "suche", "letzter_lauf.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
code_neu = index.get("letzter_code_hash") != code_hash
if zus["kandidaten_neu"] == 0 and not code_neu:
    print("Keine neuen Hypothesen und kein geänderter Code: nur letzter_lauf.json nachgeführt."); sys.exit(0)

# ---------------------------------------------------------------- Ergebnis ablegen
nr = max([s["nr"] for s in index["suchlaeufe"]] + [0]) + 1
lokal = jetzt.astimezone(ZoneInfo("Europe/Zurich"))

def fmt(r):
    return (f"{r['indikator']} {r['art']} -> {r['ziel']} {r['h']} Tage: t {r['t']:.2f}, n {r['n']}, "
            f"{r['mu']:.2f} pp je Wechsel gegenüber ACWI brutto, Hälften t {r['t1']:.2f} und {r['t2']:.2f}")

gruppen = {}
for i in zus["indikatoren"]:
    g = ("Scout" if i.startswith("neu_") else "SEC" if i.startswith("sec_") else "Paare" if i.startswith("paar_")
         else "Wetter" if i.startswith("wetter_") else "Strom" if i.startswith("strom_") else "Wikipedia" if i.startswith("wiki_")
         else "Bitcoin" if i.startswith("btc_") else "FRED")
    gruppen[g] = gruppen.get(g, 0) + 1
fund = bool(zus.get("fund"))
urteil = ("FUND – Fixierung durch Reto nötig. Siegel nicht geöffnet." if fund else
          "Kein Baustein. Validierung ab 2021 nicht angerührt (S4).")
if zus["bausteine"] and not fund:
    urteil += (f" {len(zus['bausteine'])} Baustein-Kandidat(en), aber p_lauf {zus.get('p_lauf')} > 0.05 "
               "(Placebo-Läufe erreichen ebenso viele): Zufall nicht ausgeschlossen, kein Fund.")
if zus["langzeit_hinweise"]:
    urteil += f" {len(zus['langzeit_hinweise'])} Langzeit-Hinweis(e) ohne Bestätigung auf dem ETF (kein Baustein)."

S = {
    "nr": nr, "sort": nr,
    "zeit": lokal.strftime("%-d.%-m.%Y, %H:%M (Europe/Zurich)"),
    "verfassung": "V3.6",
    "methode": zus.get("methode", "M2"),
    "entstehung": "GitHub Action «Prüfstand Suche» (V3.4 E9)" + ("" if zus["kandidaten_neu"] else ", Anlass: geänderter Code"),
    "herkunft": herkunft,
    "stichtag": "2020-12-31",
    "horizonte_tage": [1, 5, 20],
    "kandidaten": zus["kandidaten"], "kandidaten_neu": zus["kandidaten_neu"], "kandidaten_bekannt": zus["kandidaten_bekannt"],
    "kandidaten_kumuliert": zus["kandidaten_kumuliert"], "huerde_t": zus["huerde_t"],
    "familien": zus["familien"],
    "indikatoren_n": zus["indikatoren_n"],
    "ziele_n": sum(len(v) for v in zus["ziele"].values()),
    "ziele": zus["ziele"],
    "indikatoren_quellen": ", ".join(f"{g} {n}" for g, n in sorted(gruppen.items())) + f"; Paare nach paare.txt: {zus['paare']}",
    "ergebnis_alle_filter": zus["echt_alle_filter_positiv"],
    "ergebnis_vorstufe_t35": zus["echt_vorstufe_positiv"],
    "placebo_laeufe": zus.get("placebo_laeufe"),
    "placebo_bausteine_je_lauf": zus.get("placebo_bausteine_je_lauf"),
    "p_lauf": zus.get("p_lauf"),
    "fund": fund,
    "datenpruefung_verdachtstage": zus.get("datenpruefung_verdachtstage"),
    "placebo_suchlaeufe_alle_filter": zus["placebo_alle_filter_je_lauf"],
    "placebo_suchlaeufe_vorstufe": zus["placebo_vorstufe_je_lauf"],
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
json.dump(S, open(os.path.join(LERNEN, "suche", f"{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
shutil.copy(os.path.join(LAUF, "hypothesen.txt.gz"), os.path.join(LERNEN, "hypothesen.txt.gz"))
ue = open(os.path.join(LAUF, "suchlauf_ueberlebende.csv"), encoding="utf-8").read().splitlines()
open(os.path.join(LERNEN, "suche", f"{name}_ueberlebende.csv"), "w", encoding="utf-8").write("\n".join(ue[:201]) + "\n")
open(os.path.join(LERNEN, "suche", f"{name}_log.txt"), "w", encoding="utf-8").write(log[-20000:])

index["kumuliert"] = zus["kandidaten_kumuliert"]
index["suchlaeufe"].append({"nr": nr, "datei": f"suche/{name}.json", "kandidaten": zus["kandidaten"], "in_db": False})
index["reihen_letzter_suchlauf"] = zus["indikatoren"]
index["letzter_suchlauf_utc"] = jetzt.strftime("%Y-%m-%dT%H:%MZ")
index["letzter_code_hash"] = code_hash
index["methode"] = zus.get("methode", "M2")
json.dump(index, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
print(f"{name}: {zus['kandidaten']} Kandidaten, {zus['kandidaten_neu']} neu, kumuliert {zus['kandidaten_kumuliert']}, "
      f"Hürde {zus['huerde_t']}, Urteil: {urteil}")
