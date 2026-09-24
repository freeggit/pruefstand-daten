#!/usr/bin/env python3
"""Prüfstand – Suchmaschine (Suchraum, Verfassung V3.3).
Aufruf: python3 suchmaschine.py <basis main/data> [<basis claude/daten-energie/data>] [<basis claude/daten-neu/data>]
Umgebung: PS_CACHE (Zwischenspeicher), PS_KUM_VORHER (kumuliert bis Vorlauf), PS_REGISTER (optional, Register-Datei).
V3.3: Jede Hypothese (Indikator|Extremtyp|Ziel|h) zählt genau einmal; Register hypothesen.txt.gz wird nachgeführt.

Sucht Ereignisse in hochaufgelösten Reihen, nach denen ein Zielwert den Index (ACWI) schlägt.
Nur Discovery-Daten (bis STICHTAG). Validation ab STICHTAG+1 wird physisch abgeschnitten.

Kandidat = Indikator x Extremdefinition x Ziel x Horizont.
Messung je Ereignis: Eröffnung am ersten Handelstag nach Verfügbarkeit der Information bis
Schluss nach h Handelstagen, Ziel minus ACWI, in %. Ereignisse entclustert (Abstand >= max(10, h)).

Filter (alle müssen halten):
  F1 t >= max(4.5, kumulative Hürde V3.1) gegenüber der unbedingten Mehrrendite derselben Reihe
  F2 Mehrrendite je Ereignis >= KOSTEN (Wechsel hin und zurück, 4 x 15 bp)
  F3 mindestens N_MIN Ereignisse
  F4 beide Hälften der Discovery gleiches Vorzeichen, je t >= 1
  F5 Placebo (Überlebende): echte Mehrrendite besser als 99% von 10'000 Zufallsziehungen (placebo_p < 0.01)
Zusätzlich ein vollständiger Placebo-Suchlauf: alle Ereignisdaten zufällig verschoben, gleiche
Filter. Er zeigt, wie viele «Treffer» der Zufall allein liefert.
"""
import io, json, os, sys, urllib.request, zipfile
import numpy as np, pandas as pd

STICHTAG = pd.Timestamp("2020-12-31")
HORIZONTE = [1, 5, 20]          # V3.2 (E1): 126 Tage gestrichen, passt nicht zum Ziel Kurzsprung
T_MIN, T_VOR = 4.5, 3.5
T_BASIS = 4.5
KUM_VORHER = int(os.environ.get("PS_KUM_VORHER", "0"))   # Kandidaten kumuliert bis zum Vorlauf (index.json der Lernrunde)

def register_laden():
    """V3.3: Register aller je geprüften Hypothesen (Indikator|Extremtyp|Ziel|h). Zuerst claude/lernen, sonst Startbestand auf main."""
    import gzip
    quellen = [os.environ.get("PS_REGISTER")]
    if BASIS and "/main/data" in BASIS:
        quellen += [BASIS.replace("/main/data", "/claude/lernen") + "/hypothesen.txt.gz",
                    BASIS.replace("/main/data", "/main") + "/hypothesen_start.txt.gz"]
    for q in [q for q in quellen if q]:
        try:
            raw = open(q, "rb").read() if os.path.exists(q) else urllib.request.urlopen(q, timeout=120).read()
            reg = set(gzip.decompress(raw).decode("utf-8").split("\n")) - {""}
            print(f"Register: {len(reg)} bekannte Hypothesen aus {q}", flush=True)
            return reg
        except Exception as e:
            print(f"Register nicht lesbar ({q}): {e}", flush=True)
    print("Register leer: alle Kandidaten gelten als neu", flush=True)
    return set()

def huerde_kumulativ(n_kum, alpha=0.05):
    """V3.1 F1: t-Hürde, bei der über alle je geprüften Kandidaten die Chance auf einen Zufallsfund alpha bleibt (zweiseitig, Bonferroni)."""
    from statistics import NormalDist
    return max(T_BASIS, NormalDist().inv_cdf(1 - alpha / 2 / max(n_kum, 1)))
KOSTEN = 0.60          # pp je Wechsel hin und zurück
N_MIN = 30
LAG_FRED = 2           # Handelstage bis Einstieg: FRED/Wikipedia erscheinen verzögert
LAG_SOFORT = 1         # Wetter, Strom: Wert des Tages ist am Abend bekannt
RNG = np.random.default_rng(20260923)

BASIS = sys.argv[1] if len(sys.argv) > 1 else None
# Zweiter Datenweg (Claude-Code-Routine): Strom-Reihen auf dem Zweig claude/daten-energie
BASIS_E = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("PS_BASIS_ENERGIE")
# Dritter Datenweg (Quellenscout-Routine): neue Tagesreihen auf dem Zweig claude/daten-neu
BASIS_N = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("PS_BASIS_NEU")
CACHE = os.environ.get("PS_CACHE", "cache")
os.makedirs(CACHE, exist_ok=True)

def lade(rel, basis=None):
    basis = basis or BASIS
    tag = "" if basis == BASIS else ("e__" if basis == BASIS_E else "n__")
    p = os.path.join(CACHE, tag + rel.replace("/", "__"))
    if not os.path.exists(p):
        with urllib.request.urlopen(f"{basis}/{rel}", timeout=120) as r, open(p, "wb") as f:
            f.write(r.read())
    return p

# ------------------------------------------------------------------ Kurse und Ziele
man = json.load(open(lade("manifest.json")))
kurse = {}
for k, v in man["reihen"].items():
    if k.startswith("kurse:") and "fehler" not in v and v.get("granularitaet") == "1d":
        t = k.split(":", 1)[1]
        d = pd.read_csv(lade(f"kurse/{t}_d.csv"), parse_dates=["Date"]).drop_duplicates("Date").set_index("Date").sort_index()
        if "AdjClose" in d and d.AdjClose.notna().mean() > 0.99:
            f = (d.AdjClose / d.Close).astype(float)            # Dividenden und Splits: Gesamtrendite
            kurse[t] = pd.DataFrame({"Open": d.Open * f, "Close": d.AdjClose}).astype(float)
        else:
            kurse[t] = d[["Open", "Close"]].astype(float)
            print(f"Hinweis: {t} ohne AdjClose, Kursrendite ohne Dividenden", flush=True)
acwi = kurse.pop("acwi")
# V3.2 (E2): Ersatz-Benchmark vor dem ACWI-Start (28.3.2008), nur für die Discovery:
# 55% SPY + 45% EFA, fest gewichtet je Wechsel (Kauf zur Eröffnung, Verkauf zum Schluss).
BENCH_NUR = {"efa"}                                # Reihen nur für den Ersatz-Benchmark, nie Ziel
ERSATZ = {"spy": 0.55, "efa": 0.45}
ACWI_START = acwi.index[0]
if all(t in kurse for t in ERSATZ):
    vor = kurse["spy"].index.intersection(kurse["efa"].index)
    vor = vor[vor < ACWI_START]
    KAL = vor.append(acwi.index)                   # Handelskalender: SPY/EFA vor 2008, danach ACWI
    print(f"Ersatz-Benchmark 55% SPY + 45% EFA von {vor[0].date()} bis {ACWI_START.date()}", flush=True)
else:
    KAL = acwi.index
    print("Ersatz-Benchmark nicht verfügbar (EFA fehlt), Kalender = ACWI", flush=True)
ZIELE = sorted(t for t in kurse if "." not in t and t not in BENCH_NUR)   # V3 O3: Einzeltitel nie Ziel

def bench_rendite(h):
    """Rendite des Benchmarks über h Tage ab Eröffnung Tag i: ACWI, vor dem ACWI-Start der Ersatz."""
    a = acwi.reindex(KAL)
    ra = a.Close.shift(-(h - 1)) / a.Open - 1
    if KAL[0] < ACWI_START:
        re = sum(w * (kurse[t].reindex(KAL).Close.shift(-(h - 1)) / kurse[t].reindex(KAL).Open - 1) for t, w in ERSATZ.items())
        vorher = KAL < ACWI_START
        # Fenster, das über den Wechsel ACWI/Ersatz reicht, bleibt leer (nichts zusammenstückeln)
        ueber = vorher & (np.arange(len(KAL)) + h - 1 >= KAL.searchsorted(ACWI_START))
        ra = ra.where(~vorher, re).where(~ueber)
    return ra

BR = {h: bench_rendite(h) for h in HORIZONTE}

def mehrrendite(ziel, h):
    """Serie über den Kalender: Einstieg Open am Tag i, Ausstieg Close am Tag i+h-1, Ziel minus Benchmark in %."""
    z = kurse[ziel].reindex(KAL)
    ro = z.Close.shift(-(h - 1)) / z.Open - 1
    return 100 * (ro - BR[h])

MR = {(z, h): mehrrendite(z, h) for z in ZIELE for h in HORIZONTE}

# ------------------------------------------------------------------ Indikatoren (Tageswerte, punktgenau)
ind = {}      # name -> (pd.Series mit Kalendertag-Index, lag)

def fred(serie):
    f = pd.read_csv(lade(f"fred/{serie}.csv"), na_values=["."])
    f.columns = ["d", "v"]; f.d = pd.to_datetime(f.d)
    return f.dropna().set_index("d").v.astype(float)

for s, v in man["reihen"].items():
    if s.startswith("fred:") and "fehler" not in v:
        x = fred(s.split(":", 1)[1])
        if len(x) < 500 or (x.index.to_series().diff().dt.days.median() > 3):
            continue                                   # nur Tagesreihen
        n = s.split(":", 1)[1]
        ind[f"{n}_stand"] = (x, LAG_FRED)
        ind[f"{n}_d1"] = (x.diff(), LAG_FRED)
        ind[f"{n}_d5"] = (x.diff(5), LAG_FRED)

def hr_manifest():
    """Manifest des GitHub-Spiegels; Strom-Reihen vom Routine-Zweig ersetzen die gleichnamigen Einträge."""
    try:
        mh = json.load(open(lade("hr/manifest_hr.json")))
    except Exception:
        mh = {"reihen": {}}
    for v in mh["reihen"].values():
        v["_basis"] = BASIS
    if BASIS_E:
        try:
            me = json.load(open(lade("hr/manifest_energie.json", BASIS_E)))
            for k, v in me["reihen"].items():
                if v.get("dateien"):
                    v["_basis"] = BASIS_E
                    mh["reihen"][k] = v
            print(f"Strom-Zweig: {sum(1 for v in me['reihen'].values() if v.get('dateien'))} Reihen", flush=True)
        except Exception as e:
            print(f"Strom-Zweig nicht lesbar: {e}", flush=True)
    return mh if mh["reihen"] else None

mh = hr_manifest()
if mh:
    for k, v in mh["reihen"].items():
        if "fehler" in v and not v.get("dateien"):
            continue
        teile = [pd.read_csv(lade(p.replace("data/", "", 1), v["_basis"])) for p in v.get("dateien", [])]
        if not teile:
            continue
        d = pd.concat(teile, ignore_index=True)
        quelle, name = k.split(":", 1)
        if quelle == "wetter":
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            g = d.set_index("t").resample("D")
            tag = pd.DataFrame({"temp": g.temperature_2m.mean(), "regen": g.precipitation.sum(min_count=12),
                                "wind": g.wind_speed_10m.max(), "wolken": g.cloud_cover.mean()})
            for c in tag:
                s = tag[c].dropna()
                if c == "temp":   # Anomalie gegen die Tagesnorm, Norm nur aus Discovery
                    norm = s[s.index <= STICHTAG].groupby(s[s.index <= STICHTAG].index.dayofyear).mean()
                    s = s - norm.reindex(s.index.dayofyear).values
                ind[f"wetter_{name}_{c}"] = (s, LAG_SOFORT)
        elif quelle == "energie" and name.startswith("preis"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            s = d.set_index("t").preis_eur_mwh.astype(float).resample("D").mean().dropna()
            ind[f"strom_{name}"] = (s, LAG_SOFORT); ind[f"strom_{name}_d1"] = (s.diff(), LAG_SOFORT)
        elif quelle == "energie" and name.startswith("erzeugung"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            d = d.set_index("t").apply(pd.to_numeric, errors="coerce")
            tag = d.resample("D").mean()
            for c in [c for c in tag.columns if any(w in c.lower() for w in ("wind", "solar", "load", "last"))]:
                ind[f"strom_{name}_{c.lower().replace(' ', '_')[:20]}"] = (tag[c].dropna(), LAG_SOFORT)
        elif quelle == "wiki":
            s = d.set_index(pd.to_datetime(d.datum)).aufrufe.astype(float)
            ind[f"wiki_{name}_spike"] = (np.log1p(s) - np.log1p(s).rolling(28, min_periods=20).median(), LAG_FRED)

# Neue Tagesreihen nach Vertrag datum,wert: Scout-Zweig (claude/daten-neu) und SEC-Reihen auf main
def lade_vertrag(basis, manifest_rel, praefix):
    n_ok = 0
    try:
        mn = json.load(open(lade(manifest_rel, basis)))
    except Exception as e:
        print(f"{manifest_rel} nicht lesbar: {e}", flush=True)
        return 0
    for k, v in mn.get("reihen", {}).items():
        if v.get("fehler") or not v.get("datei") or v.get("status", "aktiv") != "aktiv":
            continue                                   # nur aktive Reihen; «ruhend» und «aufbau» zählen nicht
        try:
            d = pd.read_csv(lade(v["datei"].replace("data/", "", 1), basis))
            x = pd.Series(pd.to_numeric(d.wert, errors="coerce").values, index=pd.to_datetime(d.datum)).dropna().sort_index()
            x = x[~x.index.duplicated(keep="last")]
            if len(x) < 500 or x.index[0] > pd.Timestamp("2015-12-31") or x.index.to_series().diff().dt.days.median() > 3:
                continue                               # nur Tagesreihen mit Historie vor 2016
            lag = 1 + int(v.get("verfuegbar_nach_tagen", 1))
            n = praefix + k.replace(":", "_")
            ind[f"{n}_stand"] = (x, lag); ind[f"{n}_d1"] = (x.diff(), lag); ind[f"{n}_d5"] = (x.diff(5), lag)
            n_ok += 1
        except Exception as e:
            print(f"{praefix}{k}: {e}", flush=True)
    return n_ok

N_NEU = lade_vertrag(BASIS_N, "neu/manifest_neu.json", "neu_") if BASIS_N else 0
print(f"Quellenscout-Zweig: {N_NEU} Reihen", flush=True)
N_SEC = lade_vertrag(BASIS, "sec/manifest_sec.json", "sec_")
print(f"SEC-Reihen (main): {N_SEC}", flush=True)

# Bitcoin als Tagesindikator (24/7): Tagesrendite und 7-Tage-Rendite
try:
    import subprocess
    btc_p = os.path.join(CACHE, "btc.csv")
    if not os.path.exists(btc_p):
        urllib.request.urlretrieve("https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/main/data/updates/btcusd_bitstamp_1min_latest.csv", btc_p)
    b = pd.read_csv(btc_p); b.index = pd.to_datetime(b.timestamp, unit="s")
    bd = b.close.resample("D").last().dropna()
    ind["btc_r1"] = (100 * bd.pct_change(), LAG_SOFORT); ind["btc_r7"] = (100 * bd.pct_change(7), LAG_SOFORT)
except Exception as e:
    print("BTC übersprungen:", e)

# ------------------------------------------------------------------ Ereignisse (nur Vergangenheit, rollend)
def ereignisse(x, art):
    """Kalendertage mit Extrem, rein rückblickend: Perzentile/Streuung aus den 252 Vortagen."""
    x = x.dropna()
    fenster = x.shift(1).rolling(252, min_periods=150)
    if art == "hoch":   m = x > fenster.quantile(0.95)
    elif art == "tief": m = x < fenster.quantile(0.05)
    else:
        dx = x.diff(); sd = dx.shift(1).rolling(252, min_periods=150).std()
        m = (dx > 3 * sd) if art == "sprung_auf" else (dx < -3 * sd)
    return x.index[m.fillna(False).values]

def auf_kalender(tage, lag):
    """Kalendertag der Information -> Index des Einstiegs im ACWI-Kalender (lag Handelstage später)."""
    pos = KAL.searchsorted(tage, side="right") + (lag - 1)
    return pos[pos < len(KAL)]

def entclustern(pos, abstand):
    out, letzte = [], -10**9
    for p in np.sort(pos):
        if p - letzte >= abstand:
            out.append(p); letzte = p
    return np.array(out, dtype=int)

DISC_ENDE = KAL.searchsorted(STICHTAG, side="right")          # erster Validation-Index

def auswerten(pos_roh, mr, h):
    pos = entclustern(pos_roh, max(10, h))
    pos = pos[pos + h - 1 < DISC_ENDE]                           # Ausstieg noch in der Discovery
    werte = mr.values[pos]; ok = ~np.isnan(werte); pos, werte = pos[ok], werte[ok]
    n = len(werte)
    if n < 10:
        return None
    alle = mr.values[:DISC_ENDE]; alle = alle[~np.isnan(alle)]
    mu0, sd0 = alle.mean(), alle.std()
    mu = werte.mean(); t = (mu - mu0) / (sd0 / np.sqrt(n))
    mitte = KAL[pos].to_series().median()
    h1 = werte[KAL[pos] <= mitte]; h2 = werte[KAL[pos] > mitte]
    th = lambda w: (w.mean() - mu0) / (sd0 / np.sqrt(len(w))) if len(w) > 2 else 0.0
    return dict(n=n, mu=mu, mu0=mu0, t=t, t1=th(h1), t2=th(h2), erste=str(KAL[pos[0]].date()), letzte=str(KAL[pos[-1]].date()))

def suchlauf(placebo=False, seed=0):
    rng = np.random.default_rng(seed)
    zeilen = []
    for iname, (x, lag) in ind.items():
        x = x[x.index <= STICHTAG]
        for art in ("hoch", "tief", "sprung_auf", "sprung_ab"):
            tage = ereignisse(x, art)
            if len(tage) < N_MIN:
                continue
            pos = auf_kalender(tage, lag)
            if placebo:   # gleiche Anzahl, zufällige Tage im gleichen Zeitraum
                lo, hi = KAL.searchsorted(tage.min()), min(DISC_ENDE, KAL.searchsorted(tage.max()) + 1)
                pos = rng.integers(lo, max(lo + 1, hi), size=len(pos))
            for z in ZIELE:
                for h in HORIZONTE:
                    r = auswerten(pos, MR[(z, h)], h)
                    if r:
                        zeilen.append(dict(indikator=iname, art=art, ziel=z, h=h, **r))
    return pd.DataFrame(zeilen)

def filtern(df):
    df = df.copy()
    df["f_t"] = df.t.abs() >= T_MIN
    df["f_kosten"] = (df.mu - df.mu0).abs() >= KOSTEN
    df["f_n"] = df.n >= N_MIN
    df["f_stabil"] = (np.sign(df.t1) == np.sign(df.t)) & (np.sign(df.t2) == np.sign(df.t)) & (df.t1.abs() >= 1) & (df.t2.abs() >= 1)
    df["alle"] = df.f_t & df.f_kosten & df.f_n & df.f_stabil
    df["vor"] = (df.t.abs() >= T_VOR) & df.f_kosten & df.f_n & df.f_stabil
    return df

if __name__ == "__main__":
    print(f"Ziele {len(ZIELE)}: {', '.join(ZIELE)}")
    print(f"Indikatoren {len(ind)} | Discovery bis {STICHTAG.date()} | Kalender ACWI {KAL[0].date()}..{KAL[-1].date()}")
    roh = suchlauf()
    import gzip
    REG = register_laden()
    schluessel = (roh.indikator + "|" + roh.art + "|" + roh.ziel + "|" + roh.h.astype(str)).tolist()
    NEU = [k for k in set(schluessel) if k not in REG]
    KUM = KUM_VORHER + len(NEU)                     # V3.3: nur bisher ungeprüfte Hypothesen erhöhen die Hürde
    T_MIN = huerde_kumulativ(KUM)
    with open("hypothesen.txt.gz", "wb") as f:      # nachgeführtes Register, von der Lernrunde auf claude/lernen abzulegen
        f.write(gzip.compress("\n".join(sorted(REG | set(schluessel))).encode("utf-8"), mtime=0))
    print(f"V3.3: {len(roh)} Kandidaten, davon {len(NEU)} neu; kumuliert {KUM} -> Hürde t >= {T_MIN:.2f}")
    echt = filtern(roh)
    echt.to_csv("suchlauf_echt.csv", index=False)
    plac = [filtern(suchlauf(placebo=True, seed=s)) for s in range(1, 6)]
    zus = {
        "kandidaten": int(len(echt)),
        "kandidaten_neu": int(len(NEU)),
        "kandidaten_bekannt": int(len(echt) - len(NEU)),
        "kandidaten_kumuliert": int(KUM),
        "huerde_t": round(float(T_MIN), 2),
        "echt_alle_filter_positiv": int((echt.alle & (echt.t > 0)).sum()),
        "echt_alle_filter_negativ": int((echt.alle & (echt.t < 0)).sum()),
        "echt_vorstufe_positiv": int((echt.vor & (echt.t > 0)).sum()),
        "placebo_alle_filter_je_lauf": [int(p.alle.sum()) for p in plac],
        "placebo_vorstufe_je_lauf": [int(p.vor.sum()) for p in plac],
    }
    # F5 Placebo je Überlebendem: 10'000 Zufallsziehungen gleicher Grösse aus derselben Reihe
    ueber = echt[echt.vor & (echt.t > 0)].sort_values("t", ascending=False).copy()
    pz = []
    for _, r in ueber.iterrows():
        alle = MR[(r.ziel, int(r.h))].values[:DISC_ENDE]; alle = alle[~np.isnan(alle)]
        sims = np.array([RNG.choice(alle, int(r.n), replace=False).mean() for _ in range(10000)])
        pz.append(float((sims >= r.mu).mean()))
    ueber["placebo_p"] = pz
    ueber.to_csv("suchlauf_ueberlebende.csv", index=False)
    bausteine = ueber[ueber.alle & (ueber.placebo_p < 0.01)]
    zus["bausteine"] = bausteine[["indikator", "art", "ziel", "h", "n", "mu", "mu0", "t", "t1", "t2", "placebo_p"]].round(4).to_dict("records")
    zus["echt_mehr_als_staerkster_placebo"] = bool(int((echt.alle).sum()) > max(zus["placebo_alle_filter_je_lauf"]))
    pos = echt[(echt.t > 0) & (echt.n >= N_MIN)].sort_values("t", ascending=False).head(5)
    zus["staerkste_positive"] = pos[["indikator", "art", "ziel", "h", "n", "mu", "mu0", "t", "t1", "t2"]].round(3).to_dict("records")
    zus["indikatoren"] = sorted(ind)
    zus["ziele"] = ZIELE
    json.dump(zus, open("suchlauf_zusammenfassung.json", "w"), indent=1)
    print(json.dumps(zus, indent=1))
    pd.set_option("display.width", 200)
    print(ueber[["indikator", "art", "ziel", "h", "n", "mu", "mu0", "t", "t1", "t2", "placebo_p", "erste", "letzte"]].head(40).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
