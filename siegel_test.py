#!/usr/bin/env python3
"""Siegeltest (V3.6): Verfälscht alle Kurse ab 1.1.2021 und alle Ken-French-Tageswerte ab 1.1.2001 zufällig und
rechnet die Suchmaschine zweimal ohne Placebo. Jede Abweichung in n, mu, mu0, t, t1, t2 heisst: Daten nach dem
Stichtag beeinflussen die Suche (Verstoss gegen S4). Aufruf in der Action bei jeder Code-Änderung."""
import glob, os, shutil, subprocess, sys
import numpy as np, pandas as pd

ROOT = os.path.dirname(os.path.abspath(__file__))
W = "/tmp/siegel"
shutil.rmtree(W, ignore_errors=True); os.makedirs(W)
shutil.copytree(os.path.join(ROOT, "data"), f"{W}/data", ignore=shutil.ignore_patterns("hr", "sec"))
rng = np.random.default_rng(7)
for f in glob.glob(f"{W}/data/kurse/*_d.csv"):
    d = pd.read_csv(f); m = d.Date >= "2021-01-01"
    for c in ["Open", "High", "Low", "Close", "AdjClose"]:
        if c in d:
            d.loc[m, c] = d.loc[m, c] * rng.uniform(0.5, 1.5, m.sum())
    d.to_csv(f, index=False, float_format="%.4f")
for f in glob.glob(f"{W}/data/french/*aily*"):
    out = []
    for ln in open(f, encoding="latin-1").read().splitlines():
        t = ln.split(",")
        if len(t[0].strip()) == 8 and t[0].strip().isdigit() and t[0].strip() >= "20010101":
            t = [t[0]] + [f"{float(x) * rng.uniform(-3, 3):.2f}" for x in t[1:]]
        out.append(",".join(t))
    open(f, "w", encoding="latin-1").write("\n".join(out) + "\n")
shutil.copytree(os.path.join(ROOT, "data", "hr"), f"{W}/data/hr")
if os.path.isdir(os.path.join(ROOT, "data", "sec")):
    shutil.copytree(os.path.join(ROOT, "data", "sec"), f"{W}/data/sec")

def lauf(name, basis):
    d = f"{W}/{name}"; os.makedirs(d)
    env = dict(os.environ, PS_CACHE=f"{d}/c", PS_PLACEBO="0", PS_REGISTER="/dev/null", PS_PAARE=os.path.join(ROOT, "paare.txt"))
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "suchmaschine.py"), "file://" + basis], cwd=d, env=env,
                        stdout=open(f"{d}/log", "w"), stderr=subprocess.STDOUT).returncode
    if rc:
        print(open(f"{d}/log").read()[-3000:]); sys.exit(rc)
    return pd.read_csv(f"{d}/suchlauf_echt.csv.gz")

a = lauf("echt", os.path.join(ROOT, "data")); b = lauf("verf", f"{W}/data")
k = ["familie", "indikator", "art", "ziel", "h"]
m = a.merge(b, on=k, suffixes=("", "_v"), how="outer", indicator=True)
diff = {c: float((m[c] - m[c + "_v"]).abs().max()) for c in ["n", "mu", "mu0", "t", "t1", "t2"]}
nur_einer = int((m["_merge"] != "both").sum())
print(f"Siegeltest: {len(a)} Kandidaten, nur in einem Lauf {nur_einer}, grösste Abweichungen {diff}")
if nur_einer or any(v > 1e-9 for v in diff.values()):
    print("VERSTOSS S4: Daten nach dem Stichtag beeinflussen die Suche"); sys.exit(1)
print("Siegel dicht")
