#!/usr/bin/env python3
"""Siegeltest (V3.7, ab V3.9 mit Hälften-Kennzahlen und Mechanismus-Indizes): Die Suche darf nichts sehen, was nach dem Stichtag liegt (31.12.2020; Ken French 31.12.2000).
Drei Läufe ohne Placebo auf denselben Zweigen (main, Strom, Scout):
  A  Originaldaten
  B  alle Werte nach dem Stichtag zufällig verfälscht und teilweise als fehlend gesetzt (Kurse, FRED, Scout, Strom,
     Wetter, Wikipedia, SEC, Ken French)
  C  alle Zeilen nach dem Stichtag gelöscht
Die Ergebnisse (n, mu, mu0, t, t1, t2, n1, n2, mu1, mu2) müssen in A, B und C identisch sein, inklusive fehlender Werte.
Aufruf: python3 siegel_test.py (erwartet data/, optional _daten-energie/data und _daten-neu/data neben dem Skript).

V3.17 (E9 neu): Zusätzlich wird die Eingabe-Prüfsumme (eingabe.json) in A, B und C verglichen. Sie soll von Daten nach
dem Stichtag unabhängig sein. Eine Abweichung ist kein Siegelbruch (die Ergebnisse entscheiden), führt aber zu
unnötigen Suchläufen und wird darum gemeldet. PS_SIEGEL_NUR_EINGABE=1 prüft nur die Prüfsumme (schnell).

V3.18 (E9 Stufe 2, ENTWURF 27.10.2026): Variante D liest die Originaldaten über einen frisch eingefrorenen Discovery-Stand
(discovery.py). Ergebnisse und Eingabe-Prüfsumme müssen genau wie in A sein; sonst verändert der Stand die Suche.
Fassung 2 (28.10.2026, Astra-Gutachten 23, M3): Die Störproben B und C laufen zusätzlich über den tatsächlich verwendeten
Lesepfad (BS, CS): Die gestörten Daten werden frisch eingefroren und über den Stand gelesen. Die Störung ist Byte für Byte:
Nur Zeilen nach dem Stichtag (Datum nach dem 31.12.2020; Ken French nach dem 31.12.2000) werden verändert oder gelöscht,
alle übrigen Bytes bleiben gleich. Der Test prüft, dass die Störung die gelesenen Daten erreicht:
  - Familie L: In den eingefrorenen Ken-French-Tagesdateien sind die Zeilen bis 31.12.2000 gleich wie in D und Zeilen von
    2001 bis 2020 verändert (BS) bzw. gelöscht (CS); die Suche muss L selbst am 31.12.2000 kürzen.
  - Alle übrigen eingefrorenen Fassungen sind gleich wie in D (das Einfrieren entfernt jede Störung nach dem Stichtag), und
    jede eingefrorene Fassung besteht die Einfrierprüfung.
  - Nicht eingefrorene Dateien liest die Suche ungekürzt. Als abgedeckt gelten nur solche, die in D, BS und CS nicht
    eingefroren waren und deren gelesene Bytes in BS und CS anders sind als in D (siegel_abdeckung.json, für
    lauf_status.py, M4).
"""
import glob, gzip, hashlib, io, json, os, shutil, subprocess, sys
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

DATUM_ROH = DATUM + ["timestamp", "zeit"]
STICH_EPOCH = 1609459199   # 31.12.2020 23:59:59 UTC


def _nach_stichtag(w):
    """True/False: liegt das Datum (Bytes) nach dem 31.12.2020? None: nicht lesbar (Zeile bleibt unverändert)."""
    w = w.strip().strip(b'"').decode("utf-8", "replace")
    if len(w) >= 10 and w[4] == "-" and w[7] == "-":
        return w[:10] > STICH
    try:
        return float(w) > STICH_EPOCH
    except ValueError:
        return None


def bearbeite_roh(p, modus):
    """Gutachten 23, M3 (BS, CS): Störung Byte für Byte. Nur Zeilen nach dem Stichtag werden verändert oder gelöscht; Kopf,
    Anführungszeichen, Zeilenenden und alle früheren Zeilen bleiben gleich (eine nicht sicher kürzbare Datei bleibt so)."""
    roh = open(p, "rb").read()
    gz = p.endswith(".gz")
    try:
        daten = gzip.decompress(roh) if gz else roh
    except Exception:
        return
    zeilen = daten.splitlines(keepends=True)
    if not zeilen:
        return
    kopf = [f.strip().strip(b'"').decode("utf-8", "replace").lstrip("\ufeff") for f in zeilen[0].rstrip(b"\r\n").split(b",")]
    idx = next((kopf.index(c) for c in DATUM_ROH if c in kopf), None)
    if idx is None:
        return
    out, n = [zeilen[0]], 0
    for z in zeilen[1:]:
        ende = z[len(z.rstrip(b"\r\n")):]
        f = z.rstrip(b"\r\n").split(b",")
        if not (idx < len(f) and _nach_stichtag(f[idx])):
            out.append(z)
            continue
        n += 1
        if modus == "loeschen":
            continue
        for i, x in enumerate(f):
            q = x.strip()
            try:
                v = float(q.strip(b'"'))
            except ValueError:
                continue
            if i == idx:
                continue
            w = b"" if rng.random() < 0.1 else f"{v * rng.uniform(0.3, 1.7):.10g}".encode()
            f[i] = b'"' + w + b'"' if (q[:1] == b'"' and w) else w
        out.append(b",".join(f) + ende)
    if n:
        neu = b"".join(out)
        open(p, "wb").write(gzip.compress(neu, mtime=0) if gz else neu)


def bearbeite_french_roh(p, modus):
    """Wie bearbeite_french, aber Byte für Byte (Zeilenenden und Zeilen bis 31.12.2000 unverändert)."""
    out = []
    for z in open(p, "rb").read().splitlines(keepends=True):
        ende = z[len(z.rstrip(b"\r\n")):]
        t = z.rstrip(b"\r\n").split(b",")
        d0 = t[0].strip()
        if len(d0) == 8 and d0.isdigit() and d0.decode() > STICH_L.replace("-", ""):
            if modus == "loeschen":
                continue
            neu = [t[0]]
            for x in t[1:]:
                try:
                    neu.append(f"{float(x) * rng.uniform(-3, 3):.2f}".encode())
                except ValueError:
                    neu.append(x)
            out.append(b",".join(neu) + ende)
        else:
            out.append(z)
    open(p, "wb").write(b"".join(out))


def variante_roh(name, modus, wege):
    ziel = {}
    for k, pfad in wege.items():
        d = f"{W}/{name}/{k}"
        shutil.copytree(pfad, d)
        ziel[k] = d
        for p in glob.glob(f"{d}/**/*.csv*", recursive=True):
            if "/french/" in p:
                if "aily" in p:
                    bearbeite_french_roh(p, modus)
            else:
                bearbeite_roh(p, modus)
    return ziel


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

NUR_EINGABE = os.environ.get("PS_SIEGEL_NUR_EINGABE") == "1"
EINGABE = {}

def lauf(name, ziel, zusatz=None):
    d = f"{W}/{name}/lauf"; os.makedirs(d)
    env = dict(os.environ, PS_CACHE=f"{d}/c", PS_NUR_EINGABEHASH="1" if NUR_EINGABE else "0", PS_PLACEBO="0", PS_KALIBRIERUNG="0", PS_REGISTER="/dev/null",
               PS_PAARE=os.path.join(ROOT, "paare.txt"),
               PS_MECHANISMEN=os.path.join(ROOT, "mechanismen.txt"))
    for k in [k for k in env if k.startswith("PS_DISCOVERY_")]:   # V3.18: A, B, C ohne Stand; D mit frischem Stand
        env.pop(k)
    env.update(zusatz or {})
    for k, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
        if k in ziel:
            env[var] = "file://" + ziel[k]
    rc = subprocess.run([sys.executable, os.path.join(ROOT, "suchmaschine.py"), "file://" + ziel["main"]], cwd=d, env=env,
                        stdout=open(f"{d}/log", "w"), stderr=subprocess.STDOUT).returncode
    if rc:
        print(open(f"{d}/log").read()[-3000:]); sys.exit(rc)
    try:
        EINGABE[name] = json.load(open(f"{d}/eingabe.json"))
    except (OSError, ValueError):
        EINGABE[name] = None
    return None if NUR_EINGABE else pd.read_csv(f"{d}/suchlauf_echt.csv.gz")

def vergleich(a, b, name):
    k = ["familie", "indikator", "art", "ziel", "h"]
    m = a.merge(b, on=k, suffixes=("", "_v"), how="outer", indicator=True)
    nur = int((m["_merge"] != "both").sum())
    abw = {}
    for c in ["n", "mu", "mu0", "t", "t1", "t2", "n1", "n2", "mu1", "mu2"]:
        x, y = m[c].astype(float), m[c + "_v"].astype(float)
        gleich = (np.isclose(x, y, rtol=0, atol=1e-9)) | (x.isna() & y.isna())
        abw[c] = int((~gleich).sum())
    print(f"Siegeltest {name}: {len(a)} Kandidaten, nur in einem Lauf {nur}, Abweichungen je Feld {abw}")
    return nur == 0 and not any(abw.values())

def eingabe_bericht():
    h = {k: (v or {}).get("eingabe_hash") for k, v in EINGABE.items()}
    gleich = len(set(h.values())) == 1 and None not in h.values()
    teile = sorted({t for k in ("B", "C", "D", "BS", "CS") for t, w in ((EINGABE.get(k) or {}).get("teile") or {}).items()
                    if w != ((EINGABE.get("A") or {}).get("teile") or {}).get(t)})
    print(f"Eingabe-Prüfsumme (V3.17, E9) {'/'.join(h)}: {h} – " + ("unabhängig von Daten nach dem Stichtag" if gleich else
          f"ABWEICHUNG in {teile} (kein Siegelbruch, aber unnötige Suchläufe; zu klären)"))
    return gleich

STAND_AKTIV = False
try:   # V3.18 (Entwurf): Varianten über den Stand nur, wenn er eingeschaltet ist (discovery.AKTIV)
    import discovery
    STAND_AKTIV = bool(getattr(discovery, "AKTIV", False))
except ImportError:
    discovery = None


def stand(name):
    """Frisch eingefrorener Stand je Variante (wie die Suche: Einfrieren bei der ersten Verwendung)."""
    return {"PS_DISCOVERY_STAND": f"{W}/{name}/stand", "PS_DISCOVERY_EINFRIEREN": "1", "PS_DISCOVERY_BERICHT": "0"}


def _french_zeilen(b):
    """Zeilen der ersten Tabelle je Datum, wie suchmaschine.french_tag sie liest (danach folgt z. B. die gleichgewichtete)."""
    out = {}
    for z in b.decode("latin-1").splitlines():
        d0 = z.split(",", 1)[0].strip()
        if len(d0) == 8 and d0.isdigit():
            out[d0] = z
        elif out:
            break
    return out


def _datei_sha(p):
    try:
        return hashlib.sha256(open(p, "rb").read()).hexdigest()
    except OSError:
        return None


def erreicht(name, modus):
    """Gutachten 23, M3: Erreicht die Störprobe die Daten, welche die Suche über den Stand liest?"""
    vd = json.load(open(f"{W}/D/stand/stand.json", encoding="utf-8"))["dateien"]
    vx = json.load(open(f"{W}/{name}/stand/stand.json", encoding="utf-8"))["dateien"]
    inhalt = lambda v, e: open(f"{W}/{v}/stand/dateien/{e['datei']}", "rb").read()
    l_ = sorted(n for n in vd if n.startswith("french__") and "aily" in n)
    l_gut = []
    for n in l_:
        if n not in vx:
            continue
        a, b = _french_zeilen(inhalt("D", vd[n])), _french_zeilen(inhalt(name, vx[n]))
        bis2000 = ({t: z for t, z in a.items() if t <= "20001231"} == {t: z for t, z in b.items() if t <= "20001231"})
        mitte = {t: z for t, z in a.items() if "20010101" <= t <= "20201231"}
        wirkt = (any(t not in b for t in mitte) if modus == "loeschen" else any(b.get(t) != z for t, z in mitte.items()))
        if bis2000 and wirkt:
            l_gut.append(n)
    andere = sorted(n for n in vd if n not in l_ and (vx.get(n) or {}).get("sha_inhalt") != vd[n].get("sha_inhalt"))
    pr = discovery.pruefen(f"{W}/{name}/stand")
    b_ = json.load(open(f"{W}/{name}/lauf/discovery_bericht.json", encoding="utf-8"))
    ausnahmen = {x["datei"] for x in b_.get("nicht_eingefroren") or []}
    getroffen = {n for n in ausnahmen if _datei_sha(f"{W}/{name}/lauf/c/{n}") != _datei_sha(f"{W}/D/lauf/c/{n}")}
    gut = bool(l_) and len(l_gut) == len(l_) and not andere and not pr["verstoesse"]   # Familie L muss im Stand sein (Pflicht)
    print(f"Störprobe {name} über den Stand: Familie L {len(l_gut)} von {len(l_)} Ken-French-Tagesdateien bis 2000 gleich und "
          f"2001–2020 {'gelöscht' if modus == 'loeschen' else 'verändert'}" + ("" if l_ else " (Familie L nicht im Stand)")
          + f"; übrige eingefrorene Fassungen anders als in D: {len(andere)}{(' ' + str(andere[:5])) if andere else ''}; "
          f"Einfrierprüfung {'bestanden' if not pr['verstoesse'] else pr['verstoesse'][:3]}; "
          f"nicht eingefroren gelesen: {len(ausnahmen)}, davon von der Störung erreicht: {len(getroffen)}")
    return gut, getroffen


def abdeckung(ausnahmen, bestanden):
    d = {"regel": "V3.18 Fassung 2 (Gutachten 23, M4): nicht eingefrorene Dateien, die dieser Siegeltest über den Stand gestört geprüft hat",
         "lesepfad": "eingefrorener Stand", "ausnahmen_abgedeckt": sorted(ausnahmen), "bestanden": bool(bestanden)}
    json.dump(d, open(os.path.join(ROOT, "siegel_abdeckung.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)


wege = kopien()
if NUR_EINGABE:
    for n, m in (("A", None), ("B", "verfaelschen"), ("C", "loeschen")):
        lauf(n, variante(n, m, wege))
    if STAND_AKTIV:
        for n, m in (("D", None), ("BS", "verfaelschen"), ("CS", "loeschen")):
            lauf(n, (variante if n == "D" else variante_roh)(n, m, wege), stand(n))
    sys.exit(0 if eingabe_bericht() else 1)
A = lauf("A", variante("A", None, wege))
ok_b = vergleich(A, lauf("B", variante("B", "verfaelschen", wege)), "verfälscht")
ok_c = vergleich(A, lauf("C", variante("C", "loeschen", wege)), "gelöscht")
ok_d = ok_bs = ok_cs = erreicht_bs = erreicht_cs = True
if STAND_AKTIV:
    ok_d = vergleich(A, lauf("D", variante("D", None, wege), stand("D")), "eingefrorener Stand (V3.18)")
    _ea, _ed = (EINGABE.get("A") or {}).get("eingabe_hash"), (EINGABE.get("D") or {}).get("eingabe_hash")
    print(f"Eingabe-Prüfsumme A {_ea}, D (eingefrorener Stand) {_ed}: " + ("gleich" if _ea and _ea == _ed else "VERSCHIEDEN"))
    ok_d = ok_d and bool(_ea) and _ea == _ed   # V3.18: Variante D muss auch genau dieselbe Eingabe-Prüfsumme haben wie A
    ok_bs = vergleich(A, lauf("BS", variante_roh("BS", "verfaelschen", wege), stand("BS")), "verfälscht, über den Stand (Gutachten 23)")
    ok_cs = vergleich(A, lauf("CS", variante_roh("CS", "loeschen", wege), stand("CS")), "gelöscht, über den Stand (Gutachten 23)")
    erreicht_bs, aus_bs = erreicht("BS", "verfaelschen")
    erreicht_cs, aus_cs = erreicht("CS", "loeschen")
    aus_d = {x["datei"] for x in json.load(open(f"{W}/D/lauf/discovery_bericht.json", encoding="utf-8")).get("nicht_eingefroren") or []}
    abdeckung(aus_d & aus_bs & aus_cs, ok_b and ok_c and ok_d and ok_bs and ok_cs and erreicht_bs and erreicht_cs)
eingabe_bericht()
if not (ok_b and ok_c):
    print("VERSTOSS S4: Daten nach dem Stichtag beeinflussen die Suche"); sys.exit(1)
if not (ok_bs and ok_cs):
    print("VERSTOSS S4 über den Stand: Daten nach dem Stichtag (Familie L: nach 2000) beeinflussen die Suche"); sys.exit(1)
if not (erreicht_bs and erreicht_cs):
    print("STÖRPROBE UNWIRKSAM (Gutachten 23, M3): Die Störung erreicht die über den Stand gelesenen Daten nicht"); sys.exit(1)
if not ok_d:
    print("ABWEICHUNG V3.18: Der eingefrorene Stand verändert die Suche"); sys.exit(1)
print("Siegel dicht" + (", auch über den Stand (BS, CS), Stand gleich (D)" if STAND_AKTIV else ""))
