#!/usr/bin/env python3
"""Siegeltest (V3.7): Die Suche darf nichts sehen, was nach dem Stichtag liegt (31.12.2020; Ken French 31.12.2000).
Drei Läufe ohne Placebo auf denselben Zweigen (main, Strom, Scout):
  A  Originaldaten
  B  alle Werte nach dem Stichtag zufällig verfälscht und teilweise als fehlend gesetzt (Kurse, FRED, Scout, Strom,
     Wetter, Wikipedia, SEC, Ken French)
  C  alle Zeilen nach dem Stichtag gelöscht
Die Ergebnisse (n, mu, mu0, t, t1, t2) müssen in A, B und C identisch sein, inklusive fehlender Werte.
Aufruf: python3 siegel_test.py (erwartet data/, optional _daten-energie/data und _daten-neu/data neben dem Skript)."""
import glob, gzip, io, os, shutil, subprocess, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/siegel"
STICH, STICH_L = "2020-12-31", "2000-12-31"
DATUM = ["Date", "observation_date", "datum", "zeit_utc", "DATE"]
rng = np.random.default_rng(7)

def kopien():
    shutil.rmtree(W, ignore_errors=True)
    wege = {"main": os.path.join(ROOT, "data")}
    for z in ("_daten-energie", "_daten-neu"):
        if os.path.isdir(os.path.join(ROOT, z, "data")):
            wege[z] = os.path.join(ROOT, z, "data")
    return wege

def lesen(p):
    return pd.read_csv(p, compression="gzip" if p.endswith(".gz") else None, low_memory=False)

def schreiben(d, p):
    if p.endswith(".gz"):
        with gzip.open(p, "wt", encoding="utf-8") as f:
            d.to_csv(f, index=False)
    else:
        d.to_csv(p, index=False)

def bearbeite_csv(p, modus):
    try:
        d = lesen(p)
    except Exception:
        return
    spalte = next((c for c in DATUM if c in d.columns), None)
    if spalte is None:
        return
    t = pd.to_datetime(d[spalte].astype(str).str.replace("Z", ""), errors="coerce")
    nach = (t > pd.Timestamp(STICH)).values
    if not nach.any():
        return
    if modus == "loeschen":
        d = d[~nach]
    else:
        for c in d.columns:
            if c != spalte and pd.api.types.is_numeric_dtype(d[c]):
                d[c] = d[c].astype(float)
                v = d.loc[nach, c].astype(float) * rng.uniform(0.3, 1.7, nach.sum())
                v[rng.random(nach.sum()) < 0.1] = np.nan
                d.loc[nach, c] = v
    schreiben(d, p)

def bearbeite_french(p, modus):
    out = []
    for ln in open(p, encoding="latin-1").read().splitlines():
        t = ln.split(",")
        if len(t[0].strip()) == 8 and t[0].strip().isdigit() and t[0].strip() > STICH_L.replace("-", ""):
            if modus == "loeschen":
                continue
            t = [t[0]] + [f"{float(x) * rng.uniform(-3, 3):.2f}" for x in t[1:]]
        out.append(",".join(t))
    open(p, "w", encoding="latin-1").write("\n".join(out) + "\n")

def variante(name, modus, wege):
    ziel = {}
    for k, pfad in wege.items():
        d = f"{W}/{name}/{k}"
        shutil.copytree(pfad, d)
        ziel[k] = d
        if modus:
            for p in glob.glob(f"{d}/**/*.csv*", recursive=True):
                if "/french/" in p:
                    if "aily" in p:
                        bearbeite_french(p, modus)
                else:
                    bearbeite_csv(p, modus)
    return ziel

def lauf(name, ziel):
    d = f"{W}/{name}/lauf"; os.makedirs(d)
    env = dict(os.environ, PS_CACHE=f"{d}/c", PS_PLACEBO="0", PS_KALIBRIERUNG="0", PS_REGISTER="/dev/null",
               PS_PAARE=os.path.join(ROOT, "paare.txt"))
    for k, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
        if k in ziel:
            env[var] = "file://" + ziel[k]
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "suchmaschine.py"), "file://" + ziel["main"]], cwd=d, env=env,
                        stdout=open(f"{d}/log", "w"), stderr=subprocess.STDOUT).returncode
    if rc:
        print(open(f"{d}/log").read()[-3000:]); sys.exit(rc)
    return pd.read_csv(f"{d}/suchlauf_echt.csv.gz")

def vergleich(a, b, name):
    k = ["familie", "indikator", "art", "ziel", "h"]
    m = a.merge(b, on=k, suffixes=("", "_v"), how="outer", indicator=True)
    nur = int((m["_merge"] != "both").sum())
    abw = {}
    for c in ["n", "mu", "mu0", "t", "t1", "t2"]:
        x, y = m[c].astype(float), m[c + "_v"].astype(float)
        gleich = (np.isclose(x, y, rtol=0, atol=1e-9)) | (x.isna() & y.isna())
        abw[c] = int((~gleich).sum())
    print(f"Siegeltest {name}: {len(a)} Kandidaten, nur in einem Lauf {nur}, Abweichungen je Feld {abw}")
    return nur == 0 and not any(abw.values())

wege = kopien()
A = lauf("A", variante("A", None, wege))
ok_b = vergleich(A, lauf("B", variante("B", "verfaelschen", wege)), "verfälscht")
ok_c = vergleich(A, lauf("C", variante("C", "loeschen", wege)), "gelöscht")
if not (ok_b and ok_c):
    print("VERSTOSS S4: Daten nach dem Stichtag beeinflussen die Suche"); sys.exit(1)
print("Siegel dicht")
