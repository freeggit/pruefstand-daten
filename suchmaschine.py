#!/usr/bin/env python3
"""Prüfstand – Suchmaschine (Suchraum, Verfassung V3.4).
Aufruf: python3 suchmaschine.py <basis main/data> [<basis claude/daten-energie/data>] [<basis claude/daten-neu/data>]
Basis = URL (https://raw.githubusercontent.com/...) oder lokaler Pfad (file:///...).
Umgebung: PS_CACHE (Zwischenspeicher), PS_KUM_VORHER (kumuliert bis Vorlauf), PS_REGISTER (Register-Datei oder URL),
          PS_PLACEBO (Anzahl Placebo-Suchläufe, Standard 5), PS_LANGZEIT (1 = Langzeit-Familie L rechnen, Standard 1),
          PS_PAARE (Datei mit Paaren, Standard paare.txt neben diesem Skript).

Zwei Familien:
  S (Standard): Ziele = ETF des Spiegels, Benchmark ACWI (vor 28.3.2008 Ersatz 55% SPY + 45% EFA),
      Einstieg Eröffnung am ersten Handelstag nach Verfügbarkeit, Ausstieg Schluss nach h Handelstagen.
  L (Langzeit, V3.4 E11): Ziele = 11 Branchenportfolios von Ken French (Tagesrenditen ab 1926, Stellvertreter der
      Sektor-ETF), Benchmark US-Gesamtmarkt (Mkt-RF + RF). Nur Schlusskurse: Einstieg zum Schluss des Einstiegstags,
      also einen halben Tag später als in S (vorsichtig). Nur Indikatoren mit Beginn vor 1.1.1995.
      Ein L-Überlebender wird erst zum Baustein, wenn derselbe Auslöser auf dem zugeordneten ETF in S
      (2001 bis 2020) gleiches Vorzeichen und |t| >= 2 zeigt.
Nur Discovery-Daten (bis STICHTAG). Validation ab STICHTAG+1 wird nie ausgewertet (S4).

Kandidat = Indikator x Extremtyp x Ziel x Horizont. V3.3 (E6): jede Hypothese zählt einmal (Register).
Indikator-Varianten (V3.4 E12): Stand, Änderung 1/5/20 Tage, Abstand zum Jahresmittel in Standardabweichungen (z252);
Differenzen zweier Reihen nach paare.txt; Ereignisreihen (nur 0/1) nur als Stand.

Filter (alle müssen halten):
  F1 t >= max(4.5, kumulative Hürde) gegenüber der unbedingten Mehrrendite derselben Reihe
  F2 Mehrrendite je Ereignis >= KOSTEN (Wechsel hin und zurück, 4 x 15 bp)
  F3 mindestens N_MIN Ereignisse
  F4 beide Hälften der Discovery gleiches Vorzeichen, je t >= 1
  F5 Placebo (Überlebende): echte Mehrrendite besser als 99% von 10'000 Zufallsziehungen (placebo_p < 0.01)
Zusätzlich PS_PLACEBO vollständige Placebo-Suchläufe (Ereignisdaten zufällig verschoben, gleiche Filter).
"""
import gzip, io, json, os, sys, urllib.request
import numpy as np, pandas as pd

STICHTAG = pd.Timestamp("2020-12-31")
HORIZONTE = [1, 5, 20]          # V3.2 (E1)
T_MIN, T_VOR = 4.5, 3.5
T_BASIS = 4.5
KOSTEN = 0.60                   # pp je Wechsel hin und zurück
N_MIN = 30
LAG_FRED = 2                    # Handelstage bis Einstieg: FRED/Wikipedia erscheinen verzögert
LAG_SOFORT = 1                  # Wetter, Strom: Wert des Tages ist am Abend bekannt
L_BEGINN_VOR = pd.Timestamp("1995-01-01")
KUM_VORHER = int(os.environ.get("PS_KUM_VORHER", "0"))
N_PLACEBO = int(os.environ.get("PS_PLACEBO", "5"))
LANGZEIT = os.environ.get("PS_LANGZEIT", "1") == "1"
PAARE = os.environ.get("PS_PAARE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "paare.txt"))
RNG = np.random.default_rng(20260923)
# Branchenportfolio (Ken French, 12 Branchen) -> zugeordneter Sektor-ETF für die Bestätigung in S
FF_ZIELE = {"nodur": "xlp", "durbl": "xly", "manuf": "xli", "enrgy": "xle", "chems": "xlb", "buseq": "xlk",
            "telcm": "xlc", "utils": "xlu", "shops": "xly", "hlth": "xlv", "money": "xlf"}

BASIS = sys.argv[1] if len(sys.argv) > 1 else None
BASIS_E = sys.argv[2] if len(sys.argv) > 2 else os.environ.get("PS_BASIS_ENERGIE")
BASIS_N = sys.argv[3] if len(sys.argv) > 3 else os.environ.get("PS_BASIS_NEU")
CACHE = os.environ.get("PS_CACHE", "cache")
os.makedirs(CACHE, exist_ok=True)

def log(*a):
    print(*a, flush=True)

def lade(rel, basis=None):
    basis = basis or BASIS
    tag = "" if basis == BASIS else ("e__" if basis == BASIS_E else "n__")
    p = os.path.join(CACHE, tag + rel.replace("/", "__"))
    if not os.path.exists(p):
        with urllib.request.urlopen(f"{basis}/{rel}", timeout=120) as r, open(p, "wb") as f:
            f.write(r.read())
    return p

def register_laden():
    """V3.3: Register aller je geprüften Hypothesen (Indikator|Extremtyp|Ziel|h)."""
    quellen = [os.environ.get("PS_REGISTER")]
    if BASIS and "/main/data" in BASIS:
        quellen += [BASIS.replace("/main/data", "/claude/lernen") + "/hypothesen.txt.gz",
                    BASIS.replace("/main/data", "/main") + "/hypothesen_start.txt.gz"]
    for q in [q for q in quellen if q]:
        try:
            raw = open(q, "rb").read() if os.path.exists(q) else urllib.request.urlopen(q, timeout=120).read()
            reg = set(gzip.decompress(raw).decode("utf-8").split("\n")) - {""}
            log(f"Register: {len(reg)} bekannte Hypothesen aus {q}")
            return reg
        except Exception as e:
            log(f"Register nicht lesbar ({q}): {e}")
    log("Register leer: alle Kandidaten gelten als neu")
    return set()

def huerde_kumulativ(n_kum, alpha=0.05):
    """V3.1 F1: zweiseitig, Bonferroni über alle je geprüften Kandidaten."""
    from statistics import NormalDist
    return max(T_BASIS, NormalDist().inv_cdf(1 - alpha / 2 / max(n_kum, 1)))

# ================================================================== Familie S: Kurse und Ziele
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
            log(f"Hinweis: {t} ohne AdjClose, Kursrendite ohne Dividenden")
acwi = kurse.pop("acwi")
BENCH_NUR = {"efa"}
ERSATZ = {"spy": 0.55, "efa": 0.45}
ACWI_START = acwi.index[0]
if all(t in kurse for t in ERSATZ):
    vor = kurse["spy"].index.intersection(kurse["efa"].index)
    vor = vor[vor < ACWI_START]
    KAL = vor.append(acwi.index)
    log(f"Ersatz-Benchmark 55% SPY + 45% EFA von {vor[0].date()} bis {ACWI_START.date()}")
else:
    KAL = acwi.index
    log("Ersatz-Benchmark nicht verfügbar (EFA fehlt), Kalender = ACWI")
ZIELE = sorted(t for t in kurse if "." not in t and t not in BENCH_NUR)   # V3 O3: Einzeltitel nie Ziel

def bench_rendite(h):
    a = acwi.reindex(KAL)
    ra = a.Close.shift(-(h - 1)) / a.Open - 1
    if KAL[0] < ACWI_START:
        re = sum(w * (kurse[t].reindex(KAL).Close.shift(-(h - 1)) / kurse[t].reindex(KAL).Open - 1) for t, w in ERSATZ.items())
        vorher = KAL < ACWI_START
        ueber = vorher & (np.arange(len(KAL)) + h - 1 >= KAL.searchsorted(ACWI_START))
        ra = ra.where(~vorher, re).where(~ueber)
    return ra

BR = {h: bench_rendite(h) for h in HORIZONTE}

def mehrrendite(ziel, h):
    z = kurse[ziel].reindex(KAL)
    ro = z.Close.shift(-(h - 1)) / z.Open - 1
    return (100 * (ro - BR[h])).values

FAM = {"S": dict(kal=KAL, ende=KAL.searchsorted(STICHTAG, side="right"), rand=lambda h: h - 1,
                 mr={(z, h): mehrrendite(z, h) for z in ZIELE for h in HORIZONTE}, ziele=ZIELE)}

# ================================================================== Familie L: Ken French Tagesrenditen (V3.4 E11)
def french_tag(dateiname):
    """Erster Block (Value Weighted bzw. Faktoren) einer Ken-French-Tagesdatei -> DataFrame in Prozent."""
    zeilen, kopf = [], None
    for ln in open(lade(f"french/{dateiname}"), encoding="latin-1"):
        teile = [t.strip() for t in ln.strip().split(",")]
        if kopf is None:
            if ln.startswith(",") and len(teile) > 2:
                kopf = [t.lower().replace("-", "_") for t in teile[1:]]
            continue
        if len(teile[0]) == 8 and teile[0].isdigit():
            zeilen.append([teile[0]] + teile[1:])
        elif zeilen:
            break
    d = pd.DataFrame(zeilen, columns=["d"] + kopf)
    d.index = pd.to_datetime(d.pop("d"), format="%Y%m%d")
    d = d.apply(pd.to_numeric, errors="coerce")
    return d.mask(d <= -99.99)

def familie_l():
    dateien = [n for k, v in man["reihen"].items() if k.startswith("french:") for n in v.get("dateien", [])]
    ind_d = [n for n in dateien if "12_industry" in n.lower() and "daily" in n.lower()]
    fak_d = [n for n in dateien if "research_data_factors" in n.lower() and "daily" in n.lower() and "5_factors" not in n.lower()]
    if not ind_d or not fak_d:
        log("Langzeit: Ken-French-Tagesdateien noch nicht im Spiegel, Familie L entfällt")
        return None
    br = french_tag(ind_d[0]); fk = french_tag(fak_d[0])
    kal = br.index.intersection(fk.index)
    br, fk = br.reindex(kal), fk.reindex(kal)
    markt = (fk["mkt_rf"] + fk["rf"]) / 100
    def summe(r):                                  # kumulierte Log-Rendite, fehlende Tage machen das Fenster leer
        return np.log1p(r).cumsum().values
    cm = summe(markt)
    mr = {}
    for z in FF_ZIELE:
        if z not in br:
            continue
        cz = summe(br[z] / 100)
        for h in HORIZONTE:
            i = np.arange(len(kal)); j = i + h; ok = j < len(kal)
            out = np.full(len(kal), np.nan)
            # Einstieg zum Schluss von Tag i, Ausstieg zum Schluss von Tag i+h: Renditen der Tage i+1 .. i+h
            out[ok] = 100 * (np.expm1(cz[j[ok]] - cz[i[ok]]) - np.expm1(cm[j[ok]] - cm[i[ok]]))
            mr[("ff_" + z, h)] = out
    log(f"Langzeit: {len(FF_ZIELE)} Branchen von {kal[0].date()} bis {kal[-1].date()}")
    return dict(kal=kal, ende=kal.searchsorted(STICHTAG, side="right"), rand=lambda h: h,
                mr=mr, ziele=sorted({z for z, _ in mr}))

if LANGZEIT:
    try:
        fl = familie_l()
        if fl:
            FAM["L"] = fl
    except Exception as e:
        log(f"Langzeit übersprungen: {e}")

# ================================================================== Indikatoren (Tageswerte, punktgenau)
ind = {}        # name -> (Serie mit Kalendertag-Index, lag)
EREIGNIS = set()  # Ereignisreihen (nur 0/1): nur Extremtyp «hoch» (= Ereignistag), die übrigen Typen wären Doppel
basen = {}      # Basisreihe (für Paare) -> (Serie, lag)

def varianten(n, x, lag, neu_varianten=True):
    """Stand, 1/5-Tage-Änderung (wie bisher) und neu 20-Tage-Änderung und Abstand zum Jahresmittel (z252)."""
    x = x.dropna()
    if set(np.unique(x.values)) <= {0.0, 1.0}:       # Ereignisreihe (Kalender, Zinsentscheid): nur Stand
        ind[f"{n}_stand"] = (x, lag); EREIGNIS.add(f"{n}_stand"); return
    ind[f"{n}_stand"] = (x, lag); ind[f"{n}_d1"] = (x.diff(), lag); ind[f"{n}_d5"] = (x.diff(5), lag)
    if neu_varianten:
        ind[f"{n}_d20"] = (x.diff(20), lag)
        m = x.rolling(252, min_periods=150)
        ind[f"{n}_z252"] = ((x - m.mean()) / m.std(), lag)

def fred(serie):
    f = pd.read_csv(lade(f"fred/{serie}.csv"), na_values=["."])
    f.columns = ["d", "v"]; f.d = pd.to_datetime(f.d)
    return f.dropna().set_index("d").v.astype(float)

for s, v in man["reihen"].items():
    if s.startswith("fred:") and "fehler" not in v:
        x = fred(s.split(":", 1)[1])
        if len(x) < 500 or (x.index.to_series().diff().dt.days.median() > 3):
            continue
        basen[s] = (x, LAG_FRED)
        varianten(s.split(":", 1)[1], x, LAG_FRED)

def hr_manifest():
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
            log(f"Strom-Zweig: {sum(1 for v in me['reihen'].values() if v.get('dateien'))} Reihen")
        except Exception as e:
            log(f"Strom-Zweig nicht lesbar: {e}")
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
                if c == "temp":
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

def lade_vertrag(basis, manifest_rel, praefix, kurz):
    n_ok = 0
    try:
        mn = json.load(open(lade(manifest_rel, basis)))
    except Exception as e:
        log(f"{manifest_rel} nicht lesbar: {e}")
        return 0
    for k, v in mn.get("reihen", {}).items():
        if v.get("fehler") or not v.get("datei") or v.get("status", "aktiv") != "aktiv":
            continue
        try:
            d = pd.read_csv(lade(v["datei"].replace("data/", "", 1), basis))
            x = pd.Series(pd.to_numeric(d.wert, errors="coerce").values, index=pd.to_datetime(d.datum)).dropna().sort_index()
            x = x[~x.index.duplicated(keep="last")]
            if len(x) < 500 or x.index[0] > pd.Timestamp("2015-12-31") or x.index.to_series().diff().dt.days.median() > 3:
                continue
            lag = 1 + int(v.get("verfuegbar_nach_tagen", 1))
            basen[f"{kurz}:{k}"] = (x, lag)
            varianten(praefix + k.replace(":", "_"), x, lag)
            n_ok += 1
        except Exception as e:
            log(f"{praefix}{k}: {e}")
    return n_ok

N_NEU = lade_vertrag(BASIS_N, "neu/manifest_neu.json", "neu_", "neu") if BASIS_N else 0
log(f"Quellenscout-Zweig: {N_NEU} Reihen")
N_SEC = lade_vertrag(BASIS, "sec/manifest_sec.json", "sec_", "sec")
log(f"SEC-Reihen (main): {N_SEC}")

# Paare (V3.4 E12)
N_PAARE = 0
if os.path.exists(PAARE):
    for ln in open(PAARE, encoding="utf-8"):
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        name, a, b, art = [t.strip() for t in ln.split(";")[:4]]
        if a not in basen or b not in basen:
            log(f"Paar {name}: {a if a not in basen else b} fehlt, übersprungen")
            continue
        (xa, la), (xb, lb) = basen[a], basen[b]
        j = pd.concat([xa, xb], axis=1, join="inner").dropna()
        if art == "logratio":
            j = j[(j.iloc[:, 0] > 0) & (j.iloc[:, 1] > 0)]
            s = np.log(j.iloc[:, 0]) - np.log(j.iloc[:, 1])
        else:
            s = j.iloc[:, 0] - j.iloc[:, 1]
        if len(s) < 500:
            continue
        varianten(f"paar_{name}", s, max(la, lb)); N_PAARE += 1
log(f"Paare: {N_PAARE}")

try:
    btc_p = os.path.join(CACHE, "btc.csv")
    if not os.path.exists(btc_p):
        urllib.request.urlretrieve("https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/main/data/updates/btcusd_bitstamp_1min_latest.csv", btc_p)
    b = pd.read_csv(btc_p); b.index = pd.to_datetime(b.timestamp, unit="s")
    bd = b.close.resample("D").last().dropna()
    ind["btc_r1"] = (100 * bd.pct_change(), LAG_SOFORT); ind["btc_r7"] = (100 * bd.pct_change(7), LAG_SOFORT)
except Exception as e:
    log("BTC übersprungen:", e)

# ================================================================== Ereignisse und Auswertung
def ereignisse(x, art, ist_ereignis=False):
    """Kalendertage mit Extrem, rein rückblickend: Perzentile/Streuung aus den 252 Vortagen.
    Ereignisreihen (0/1): jeder Tag mit Wert 1 (Label «hoch»), unabhängig von der Häufigkeit."""
    x = x.dropna()
    if ist_ereignis:
        return x.index[(x == 1).values]
    fenster = x.shift(1).rolling(252, min_periods=150)
    if art == "hoch":   m = x > fenster.quantile(0.95)
    elif art == "tief": m = x < fenster.quantile(0.05)
    else:
        dx = x.diff(); sd = dx.shift(1).rolling(252, min_periods=150).std()
        m = (dx > 3 * sd) if art == "sprung_auf" else (dx < -3 * sd)
    return x.index[m.fillna(False).values]

def entclustern(pos, abstand):
    out, letzte = [], -10**9
    for p in np.sort(pos):
        if p - letzte >= abstand:
            out.append(p); letzte = p
    return np.array(out, dtype=int)

BASIS_STAT = {}
def basis_stat(fam, z, h):
    k = (fam, z, h)
    if k not in BASIS_STAT:
        f = FAM[fam]; a = f["mr"][(z, h)][:f["ende"]]; a = a[~np.isnan(a)]
        BASIS_STAT[k] = (a.mean(), a.std(), a)
    return BASIS_STAT[k]

def auswerten(fam, pos_roh, z, h):
    f = FAM[fam]; kal = f["kal"]
    pos = entclustern(pos_roh, max(10, h))
    pos = pos[pos + f["rand"](h) < f["ende"]]                 # Ausstieg noch in der Discovery
    werte = f["mr"][(z, h)][pos]; ok = ~np.isnan(werte); pos, werte = pos[ok], werte[ok]
    n = len(werte)
    if n < 10:
        return None
    mu0, sd0, _ = basis_stat(fam, z, h)
    mu = werte.mean(); t = (mu - mu0) / (sd0 / np.sqrt(n))
    mitte = np.median(pos)
    h1, h2 = werte[pos <= mitte], werte[pos > mitte]
    th = lambda w: (w.mean() - mu0) / (sd0 / np.sqrt(len(w))) if len(w) > 2 else 0.0
    # Zusatzmass (nur Bericht, kein Filter): t mit der grösseren von beiden Streuungen, schützt vor Ereignissen in unruhigen Zeiten
    t_rob = (mu - mu0) / (max(sd0, werte.std(ddof=1)) / np.sqrt(n))
    return dict(n=n, mu=mu, mu0=mu0, t=t, t_rob=t_rob, t1=th(h1), t2=th(h2), erste=str(kal[pos[0]].date()), letzte=str(kal[pos[-1]].date()))

def suchlauf(placebo=False, seed=0):
    rng = np.random.default_rng(seed)
    zeilen = []
    for iname, (x, lag) in ind.items():
        x = x[x.index <= STICHTAG].dropna()
        if x.empty:
            continue
        for art in (("hoch",) if iname in EREIGNIS else ("hoch", "tief", "sprung_auf", "sprung_ab")):
            tage = ereignisse(x, art, iname in EREIGNIS)
            if len(tage) < N_MIN:
                continue
            for fam, f in FAM.items():
                if fam == "L" and x.index[0] >= L_BEGINN_VOR:
                    continue                                   # Langzeit nur für Reihen mit Beginn vor 1995
                kal = f["kal"]
                pos = kal.searchsorted(tage, side="right") + (lag - 1)
                pos = pos[pos < len(kal)]
                if len(pos) == 0:
                    continue
                if placebo:
                    lo, hi = kal.searchsorted(tage.min()), min(f["ende"], kal.searchsorted(tage.max()) + 1)
                    pos = rng.integers(lo, max(lo + 1, hi), size=len(pos))
                for z in f["ziele"]:
                    for h in HORIZONTE:
                        r = auswerten(fam, pos, z, h)
                        if r:
                            zeilen.append(dict(familie=fam, indikator=iname, art=art, ziel=z, h=h, **r))
    return pd.DataFrame(zeilen)

def filtern(df, t_min):
    df = df.copy()
    df["f_t"] = df.t.abs() >= t_min
    df["f_kosten"] = (df.mu - df.mu0).abs() >= KOSTEN
    df["f_n"] = df.n >= N_MIN
    df["f_stabil"] = (np.sign(df.t1) == np.sign(df.t)) & (np.sign(df.t2) == np.sign(df.t)) & (df.t1.abs() >= 1) & (df.t2.abs() >= 1)
    df["alle"] = df.f_t & df.f_kosten & df.f_n & df.f_stabil
    df["vor"] = (df.t.abs() >= T_VOR) & df.f_kosten & df.f_n & df.f_stabil
    return df

SPALTEN = ["familie", "indikator", "art", "ziel", "h", "n", "mu", "mu0", "t", "t_rob", "t1", "t2"]

if __name__ == "__main__":
    import time
    t0 = time.time()
    log(f"Familien: {', '.join(FAM)} | Ziele S {len(ZIELE)}: {', '.join(ZIELE)}")
    if "L" in FAM:
        log(f"Ziele L: {', '.join(FAM['L']['ziele'])}")
    log(f"Indikatoren {len(ind)} | Discovery bis {STICHTAG.date()} | Kalender S {KAL[0].date()}..{KAL[-1].date()}")
    roh = suchlauf()
    log(f"Echter Suchlauf: {len(roh)} Kandidaten in {(time.time() - t0) / 60:.1f} min")
    REG = register_laden()
    schluessel = (roh.indikator + "|" + roh.art + "|" + roh.ziel + "|" + roh.h.astype(str)).tolist()
    NEU = sorted(set(schluessel) - REG)
    KUM = KUM_VORHER + len(NEU)
    T_MIN = huerde_kumulativ(KUM)
    with open("hypothesen.txt.gz", "wb") as f:
        f.write(gzip.compress("\n".join(sorted(REG | set(schluessel))).encode("utf-8"), mtime=0))
    log(f"V3.3: {len(roh)} Kandidaten, davon {len(NEU)} neu; kumuliert {KUM} -> Hürde t >= {T_MIN:.2f}")
    echt = filtern(roh, T_MIN)
    echt.to_csv("suchlauf_echt.csv.gz", index=False)
    plac = []
    for s in range(1, N_PLACEBO + 1):
        plac.append(filtern(suchlauf(placebo=True, seed=s), T_MIN))
        log(f"Placebo {s}/{N_PLACEBO}: alle Filter {int(plac[-1].alle.sum())}, Vorstufe {int(plac[-1].vor.sum())}")
    zus = {
        "kandidaten": int(len(echt)),
        "kandidaten_neu": int(len(NEU)),
        "kandidaten_bekannt": int(len(set(schluessel)) - len(NEU)),
        "kandidaten_kumuliert": int(KUM),
        "huerde_t": round(float(T_MIN), 2),
        "familien": {fam: int((echt.familie == fam).sum()) for fam in FAM},
        "echt_alle_filter_positiv": int((echt.alle & (echt.t > 0)).sum()),
        "echt_alle_filter_negativ": int((echt.alle & (echt.t < 0)).sum()),
        "echt_vorstufe_positiv": int((echt.vor & (echt.t > 0)).sum()),
        "placebo_alle_filter_je_lauf": [int(p.alle.sum()) for p in plac],
        "placebo_vorstufe_je_lauf": [int(p.vor.sum()) for p in plac],
    }
    # F5 je Überlebendem: 10'000 Zufallsziehungen gleicher Grösse aus derselben Reihe
    ueber = echt[echt.vor & (echt.t > 0)].sort_values("t", ascending=False).copy()
    pz, tb = [], []
    for _, r in ueber.iterrows():
        _, _, alle = basis_stat(r.familie, r.ziel, int(r.h))
        sims = np.array([RNG.choice(alle, int(r.n), replace=False).mean() for _ in range(10000)])
        pz.append(float((sims >= r.mu).mean()))
        tb.append(np.nan)
        if r.familie == "L":                           # Bestätigung auf dem zugeordneten ETF in S
            etf = FF_ZIELE[r.ziel[3:]]
            m = echt[(echt.familie == "S") & (echt.indikator == r.indikator) & (echt.art == r.art) & (echt.ziel == etf) & (echt.h == r.h)]
            tb[-1] = float(m.t.iloc[0]) if len(m) else np.nan
    ueber["placebo_p"] = pz
    ueber["t_bestaetigung_etf"] = tb
    ueber.to_csv("suchlauf_ueberlebende.csv", index=False)
    kern = ueber.alle & (ueber.placebo_p < 0.01)
    best = (ueber.familie == "S") | ((np.sign(ueber.t_bestaetigung_etf) == np.sign(ueber.t)) & (ueber.t_bestaetigung_etf.abs() >= 2))
    bausteine = ueber[kern & best]
    hinweise = ueber[kern & ~best]
    zus["bausteine"] = bausteine[SPALTEN + ["placebo_p", "t_bestaetigung_etf"]].round(4).to_dict("records")
    zus["langzeit_hinweise"] = hinweise[SPALTEN + ["placebo_p", "t_bestaetigung_etf"]].round(4).to_dict("records")
    zus["echt_mehr_als_staerkster_placebo"] = bool(int(echt.alle.sum()) > max(zus["placebo_alle_filter_je_lauf"] or [0]))
    pos = echt[(echt.t > 0) & (echt.n >= N_MIN)].sort_values("t", ascending=False).head(10)
    zus["staerkste_positive"] = pos[SPALTEN].round(3).to_dict("records")
    zus["indikatoren_n"] = len(ind)
    zus["indikatoren"] = sorted(ind)
    zus["ziele"] = {fam: f["ziele"] for fam, f in FAM.items()}
    zus["paare"] = N_PAARE
    zus["dauer_min"] = round((time.time() - t0) / 60, 1)
    json.dump(zus, open("suchlauf_zusammenfassung.json", "w"), indent=1)
    kurz = {k: v for k, v in zus.items() if k not in ("indikatoren",)}
    log(json.dumps(kurz, indent=1))
    pd.set_option("display.width", 220)
    log(ueber[SPALTEN + ["placebo_p", "t_bestaetigung_etf", "erste", "letzte"]].head(40).to_string(index=False, float_format=lambda v: f"{v:.2f}"))
