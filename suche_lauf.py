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
"""
import gzip, hashlib, json, os, shutil, subprocess, sys
from datetime import datetime, timezone
from zoneinfo import ZoneInfo

ROOT = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, ROOT)
from integritaet import ohne_nan  # noqa: E402

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
           PS_REGISTER=reg, PS_PAARE=os.path.join(ROOT, "paare.txt"), PS_MECHANISMEN=os.path.join(ROOT, "mechanismen.txt"))
env.setdefault("PS_PLACEBO", "200")
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

code_hash = hashlib.sha256("".join(sha(os.path.join(ROOT, f)) or "" for f in ("suchmaschine.py", "paare.txt", "suche_lauf.py", "mechanismen.txt", "korrekturen_neu.json")).encode()).hexdigest()[:16]
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
vollarchiv = bool(zus["kandidaten_neu"] > 0 or code_neu)
vorher = list(index.get("reihen_letzter_suchlauf") or [])
entfallen = sorted(set(vorher) - set(zus["indikatoren"])); neu_dabei = sorted(set(zus["indikatoren"]) - set(vorher))
kern = {"kandidaten": zus["kandidaten"], "kandidaten_neu": zus["kandidaten_neu"], "huerde_t": zus["huerde_t"],
        "echt_bestes_t": zus.get("echt_bestes_t"), "p_lauf": zus.get("p_lauf"),
        "kandidaten_stufe_d": len(zus["bausteine"]), "fehlalarmrate": zus.get("fehlalarmrate"), "placebo_laeufe": zus.get("placebo_laeufe")}
s_schreiben = bool(vollarchiv or ergebnis_neu)
nr = max([s["nr"] for s in index["suchlaeufe"]] + [0]) + 1
letzter_s = next((s["datei"] for s in reversed(index["suchlaeufe"]) if s.get("datei")), None)
eintrag = laufeintrag({
    "stufen": {"suche": "vollständig"}, "herkunft": herkunft, "ergebnis_hash": ergebnis_hash, **kern,
    "reihen": {"vorhanden_n": len(zus["indikatoren"]), "vorlauf_n": len(vorher), "entfallen_gegen_vorlauf": entfallen,
               "neu_gegen_vorlauf": neu_dabei, "erwartet_und_gesperrt": zus.get("reihen_bericht"),
               "liste": "index.json Feld reihen_letzter_suchlauf"},
    "ausgaben": {"s_dokument": f"suche/S{nr:04d}.json" if s_schreiben else letzter_s,
                 "s_dokument_art": "neu in diesem Lauf" if s_schreiben else "unverändert: Ergebnisse dieses Laufs sind Zeichen für Zeichen gleich wie im genannten Dokument",
                 "vollarchiv": f"suche/S{nr:04d}_alle.csv.gz" if vollarchiv else index.get("letztes_vollarchiv"),
                 "vollarchiv_art": "neu in diesem Lauf" if vollarchiv else "aus einem früheren Lauf (keine neuen Schlüssel, Code unverändert)"},
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

index["kumuliert"] = zus["kandidaten_kumuliert"]
index["suchlaeufe"].append({"nr": nr, "datei": f"suche/{name}.json", "kandidaten": zus["kandidaten"], "in_db": False})
index["letzter_ergebnis_hash"] = ergebnis_hash
index["letzter_suchlauf_utc"] = jetzt.strftime("%Y-%m-%dT%H:%MZ")
index["letzter_code_hash"] = code_hash
index["methode"] = zus.get("methode", "M4")
schreibe_json(index, ip)
print(f"{name}: {zus['kandidaten']} Kandidaten, {zus['kandidaten_neu']} neu, kumuliert {zus['kandidaten_kumuliert']}, "
      f"Hürde {zus['huerde_t']}, Urteil: {urteil}")
