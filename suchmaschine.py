#!/usr/bin/env python3
"""Prüfstand – Suchmaschine (Suchraum, Verfassung V3.6, Methode M2).
Aufruf: python3 suchmaschine.py <basis main/data> [<basis claude/daten-energie/data>] [<basis claude/daten-neu/data>]
Basis = URL (https://raw.githubusercontent.com/...) oder lokaler Pfad (file:///...).
Umgebung: PS_CACHE, PS_KUM_VORHER (kumuliert bis Vorlauf), PS_REGISTER (Register), PS_PLACEBO (Placebo-Läufe, Standard 20),
          PS_LANGZEIT (1 = Familie L), PS_PAARE (paare.txt), PS_BASIS_ENERGIE, PS_BASIS_NEU.

Methode M2 (V3.6, 25.9.2026, nach externer Gegenprüfung):
- Siegel: jede Rendite, auch in Vergleichswerten und Zufallsziehungen, endet spätestens am STICHTAG (S4).
- Verfügbarkeit (D2): Tagesfrist je Quelle; H.10-Devisenkurse der Fed ab 2009 erst nach der Wochenpublikation (Montag),
  EIA-Spotpreise (Öl, Gas, Brent, Propan) erst nach der Wochenpublikation (Mittwoch der Folgewoche),
  Wetter (Reanalyse) 5 Handelstage. Ereignisse vor Beginn des Kurskalenders werden verworfen (keine Phantomereignisse).
- Datenprüfung (S1): Eröffnungskurs mit Sprung über 5% zum Vortagesschluss bei Schlusskurs innerhalb 2% gilt als fehlend.
- Temperaturnorm nur aus Vorjahren (D4).
- Vergleich (Normalfall) nur über die Laufzeit des Indikators; zwei Hälften am festen Mittelpunkt dieser Laufzeit,
  je mit eigener Referenz.
- F1 mit robustem t: Streuung = grössere von Referenz- und Ereignisstreuung (früher F6).
- F2 = mittlere Mehrrendite gegenüber ACWI >= 0.60 pp (Vorzeichen des Befunds), nicht Differenz zum Normalfall.
- F5 = Bootstrap aus dem Referenzfenster, p = (k+1)/(N+1).
- Placebo: Ereignisdaten je Indikator als Block verschoben (Häufung bleibt), ganze Auswahl inkl. F5 und ETF-Bestätigung.
  Fund nur, wenn Bausteine vorliegen und der Anteil Placebo-Läufe mit mindestens so vielen Bausteinen <= 5% ist.
- Familie L (Ken French ab 1926) nur bis 31.12.2000; Bestätigung auf dem ETF in S 2001–2020 (zeitlich getrennt).
- Register mit Methodenversion: Schlüssel «M2|Indikator|Extremtyp|Ziel|h»; jede M2-Hypothese zählt einmal.
"""
import gzip, hashlib, io, json, os, sys, time, urllib.request
import numpy as np, pandas as pd

METHODE = "M2"
STICHTAG = pd.Timestamp("2020-12-31")
L_ENDE = pd.Timestamp("2000-12-31")            # V3.6: Langzeit-Discovery endet vor der ETF-Periode
HORIZONTE = [1, 5, 20]
T_BASIS, T_VOR, T_HAELFTE, T_BEST = 4.5, 3.5, 1.0, 2.0
KOSTEN = 0.60
N_MIN = 30
LAG_FRED, LAG_SOFORT, LAG_WETTER = 2, 1, 6      # Handelstage bis Einstieg (1 = nächster Handelstag)
L_BEGINN_VOR = pd.Timestamp("1995-01-01")
KUM_VORHER = int(os.environ.get("PS_KUM_VORHER", "0"))
N_PLACEBO = int(os.environ.get("PS_PLACEBO", "20"))
N_F5 = 10000
LANGZEIT = os.environ.get("PS_LANGZEIT", "1") == "1"
PAARE = os.environ.get("PS_PAARE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "paare.txt"))
FF_ZIELE = {"nodur": "xlp", "durbl": "xly", "manuf": "xli", "enrgy": "xle", "chems": "xlb", "buseq": "xlk",
            "telcm": "xlc", "utils": "xlu", "shops": "xly", "hlth": "xlv", "money": "xlf"}
# Publikationsrhythmus je Basisreihe (D2). Alles andere: Tagesfrist.
H10 = {"fred:DEXSZUS", "fred:DTWEXBGS", "fred:DEXJPUS", "fred:DEXUSEU", "fred:DEXUSUK", "fred:DEXCAUS", "fred:DEXUSAL"}
H10_SCOUT = ("fred_usdjpy", "fred_fx_lang")
EIA = {"fred:DCOILWTICO", "fred:DHHNGSP", "fred:DCOILBRENTEU", "fred:DPROPANEMBTX"}
EIA_SCOUT = ("fred_brent", "fred_propane")

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
    quellen = [os.environ.get("PS_REGISTER")]
    if BASIS and "/main/data" in BASIS:
        quellen += [BASIS.replace("/main/data", "/claude/lernen") + "/hypothesen.txt.gz",
                    BASIS.replace("/main/data", "/main") + "/hypothesen_start.txt.gz"]
    for q in [q for q in quellen if q]:
        try:
            raw = open(q, "rb").read() if os.path.exists(q) else urllib.request.urlopen(q, timeout=120).read()
            reg = set(gzip.decompress(raw).decode("utf-8").split("\n")) - {""}
            log(f"Register: {len(reg)} Einträge aus {q}")
            return reg
        except Exception as e:
            log(f"Register nicht lesbar ({q}): {e}")
    return set()

def huerde_kumulativ(n_kum, alpha=0.05):
    from statistics import NormalDist
    return max(T_BASIS, NormalDist().inv_cdf(1 - alpha / 2 / max(n_kum, 1)))

# ================================================================== Familie S: Kurse, Datenprüfung, Ziele
man = json.load(open(lade("manifest.json")))
kurse, VERDACHT = {}, {}
for k, v in man["reihen"].items():
    if k.startswith("kurse:") and "fehler" not in v and v.get("granularitaet") == "1d":
        t = k.split(":", 1)[1]
        d = pd.read_csv(lade(f"kurse/{t}_d.csv"), parse_dates=["Date"]).drop_duplicates("Date").set_index("Date").sort_index()
        vor = d.Close.shift(1)
        verdacht = ((d.Open / vor - 1).abs() > 0.05) & ((d.Close / vor - 1).abs() < 0.02)
        if verdacht.any():
            VERDACHT[t] = [str(x.date()) for x in d.index[verdacht]]
            d.loc[verdacht, "Open"] = np.nan                  # fehlt, wird nicht geschätzt (D3)
        if "AdjClose" in d and d.AdjClose.notna().mean() > 0.99:
            f = (d.AdjClose / d.Close).astype(float)
            kurse[t] = pd.DataFrame({"Open": d.Open * f, "Close": d.AdjClose}).astype(float)
        else:
            kurse[t] = d[["Open", "Close"]].astype(float)
if VERDACHT:
    log(f"Datenprüfung: verdächtige Eröffnungskurse als fehlend gesetzt: {VERDACHT}")
acwi = kurse.pop("acwi")
BENCH_NUR = {"efa"}
ERSATZ = {"spy": 0.55, "efa": 0.45}
ACWI_START = acwi.index[0]
if all(t in kurse for t in ERSATZ):
    vor = kurse["spy"].index.intersection(kurse["efa"].index)
    KAL = vor[vor < ACWI_START].append(acwi.index)
else:
    KAL = acwi.index
ZIELE = sorted(t for t in kurse if "." not in t and t not in BENCH_NUR)

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
    return (100 * (z.Close.shift(-(h - 1)) / z.Open - 1 - BR[h])).values

FAM = {"S": dict(kal=KAL, ende=KAL.searchsorted(STICHTAG, side="right"), rand=lambda h: h - 1,
                 mr={(z, h): mehrrendite(z, h) for z in ZIELE for h in HORIZONTE}, ziele=ZIELE)}

# ================================================================== Familie L (bis 2000)
def french_tag(dateiname):
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
        log("Langzeit: Ken-French-Tagesdateien fehlen, Familie L entfällt"); return None
    br = french_tag(ind_d[0]); fk = french_tag(fak_d[0])
    kal = br.index.intersection(fk.index)
    br, fk = br.reindex(kal), fk.reindex(kal)
    cm = np.log1p((fk["mkt_rf"] + fk["rf"]) / 100).cumsum().values
    mr = {}
    for z in FF_ZIELE:
        if z not in br:
            continue
        cz = np.log1p(br[z] / 100).cumsum().values
        for h in HORIZONTE:
            i = np.arange(len(kal)); j = i + h; ok = j < len(kal)
            out = np.full(len(kal), np.nan)
            out[ok] = 100 * (np.expm1(cz[j[ok]] - cz[i[ok]]) - np.expm1(cm[j[ok]] - cm[i[ok]]))
            mr[("ff_" + z, h)] = out
    return dict(kal=kal, ende=kal.searchsorted(L_ENDE, side="right"), rand=lambda h: h, mr=mr, ziele=sorted({z for z, _ in mr}))

if LANGZEIT:
    try:
        fl = familie_l()
        if fl:
            FAM["L"] = fl
    except Exception as e:
        log(f"Langzeit übersprungen: {e}")

# Präfixsummen für Vergleichswerte in beliebigen Fenstern (ohne NaN)
PRAEFIX = {}
for fam, f in FAM.items():
    for key, a in f["mr"].items():
        ok = ~np.isnan(a); v = np.where(ok, a, 0.0)
        PRAEFIX[(fam,) + key] = (np.concatenate([[0], np.cumsum(v)]), np.concatenate([[0], np.cumsum(v * v)]),
                                 np.concatenate([[0], np.cumsum(ok)]))

def fenster(fam, z, h, lo, hi):
    """Mittel und Streuung der Mehrrendite für Einstiege lo..hi-1, nur Fenster mit Ausstieg <= STICHTAG (Siegel)."""
    f = FAM[fam]; hi = min(hi, f["ende"] - f["rand"](h)); lo = max(lo, 0)
    if hi - lo < 30:
        return None
    s, q, c = PRAEFIX[(fam, z, h)]
    n = c[hi] - c[lo]
    if n < 30:
        return None
    m = (s[hi] - s[lo]) / n
    var = max((q[hi] - q[lo]) / n - m * m, 0.0) * n / (n - 1)
    return m, np.sqrt(var)

# ================================================================== Indikatoren
ind = {}          # name -> (Serie, Regeln der Verfügbarkeit)
EREIGNIS, QUELLE, basen = set(), {}, {}

def quelle_von(name):
    if name in QUELLE:
        return QUELLE[name]
    for p, q in (("wetter_", "wetter"), ("strom_", "strom"), ("wiki_", "wikipedia"), ("btc_", "bitcoin")):
        if name.startswith(p):
            return q
    return "andere"

def regeln_fuer(basis_key, lag):
    if basis_key in H10 or any(basis_key.startswith(f"neu:{s}:") for s in H10_SCOUT):
        return [("h10",)]
    if basis_key in EIA or any(basis_key.startswith(f"neu:{s}:") for s in EIA_SCOUT):
        return [("eia",)]
    return [("tag", lag)]

def varianten(n, x, regeln, quelle=None):
    x = x.dropna()
    for suffix in ("_stand", "_d1", "_d5", "_d20", "_z252"):
        if quelle:
            QUELLE[n + suffix] = quelle
    if set(np.unique(x.values)) <= {0.0, 1.0}:
        ind[f"{n}_stand"] = (x, regeln); EREIGNIS.add(f"{n}_stand"); return
    m = x.rolling(252, min_periods=150)
    for suffix, s in (("_stand", x), ("_d1", x.diff()), ("_d5", x.diff(5)), ("_d20", x.diff(20)), ("_z252", (x - m.mean()) / m.std())):
        ind[n + suffix] = (s, regeln)

def fred(serie):
    f = pd.read_csv(lade(f"fred/{serie}.csv"), na_values=["."])
    f.columns = ["d", "v"]; f.d = pd.to_datetime(f.d)
    return f.dropna().set_index("d").v.astype(float)

for s, v in man["reihen"].items():
    if s.startswith("fred:") and "fehler" not in v:
        x = fred(s.split(":", 1)[1])
        if len(x) < 500 or (x.index.to_series().diff().dt.days.median() > 3):
            continue
        r = regeln_fuer(s, LAG_FRED)
        basen[s] = (x, r)
        varianten(s.split(":", 1)[1], x, r, quelle=s)

def norm_vorjahre(s):
    """Tagesnorm (±7 Tage geglättet) nur aus Vorjahren, mindestens 3 Vorjahre (D4)."""
    df = pd.DataFrame({"v": s.values, "j": s.index.year, "t": np.minimum(s.index.dayofyear, 365)})
    tab = df.pivot_table(index="j", columns="t", values="v", aggfunc="mean").reindex(columns=range(1, 366))
    ext = pd.concat([tab.iloc[:, -7:], tab, tab.iloc[:, :7]], axis=1)
    ext.columns = range(ext.shape[1])
    sm = ext.T.rolling(15, center=True, min_periods=5).mean().T.iloc[:, 7:-7]
    sm.columns = range(1, 366)
    cs = sm.fillna(0).cumsum().shift(1); cn = sm.notna().cumsum().shift(1)
    norm = (cs / cn).where(cn >= 3)
    return pd.Series(norm.stack().reindex(list(zip(df.j, df.t))).values, index=s.index)

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
                    v["_basis"] = BASIS_E; mh["reihen"][k] = v
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
                    s = (s - norm_vorjahre(s)).dropna()
                ind[f"wetter_{name}_{c}"] = (s, [("tag", LAG_WETTER)])
        elif quelle == "energie" and name.startswith("preis"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            s = d.set_index("t").preis_eur_mwh.astype(float).resample("D").mean().dropna()
            ind[f"strom_{name}"] = (s, [("tag", LAG_SOFORT)]); ind[f"strom_{name}_d1"] = (s.diff(), [("tag", LAG_SOFORT)])
        elif quelle == "energie" and name.startswith("erzeugung"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            d = d.set_index("t").apply(pd.to_numeric, errors="coerce")
            tag = d.resample("D").mean()
            for c in [c for c in tag.columns if any(w in c.lower() for w in ("wind", "solar", "load", "last"))]:
                ind[f"strom_{name}_{c.lower().replace(' ', '_')[:20]}"] = (tag[c].dropna(), [("tag", LAG_SOFORT)])
        elif quelle == "wiki":
            s = d.set_index(pd.to_datetime(d.datum)).aufrufe.astype(float)
            ind[f"wiki_{name}_spike"] = (np.log1p(s) - np.log1p(s).rolling(28, min_periods=20).median(), [("tag", LAG_FRED)])

def lade_vertrag(basis, manifest_rel, praefix, kurz):
    n_ok = 0
    try:
        mn = json.load(open(lade(manifest_rel, basis)))
    except Exception as e:
        log(f"{manifest_rel} nicht lesbar: {e}"); return 0
    for k, v in mn.get("reihen", {}).items():
        if v.get("fehler") or not v.get("datei") or v.get("status", "aktiv") != "aktiv":
            continue
        try:
            d = pd.read_csv(lade(v["datei"].replace("data/", "", 1), basis))
            x = pd.Series(pd.to_numeric(d.wert, errors="coerce").values, index=pd.to_datetime(d.datum)).dropna().sort_index()
            x = x[~x.index.duplicated(keep="last")]
            if len(x) < 500 or x.index[0] > pd.Timestamp("2015-12-31") or x.index.to_series().diff().dt.days.median() > 3:
                continue
            r = regeln_fuer(f"{kurz}:{k}", 1 + int(v.get("verfuegbar_nach_tagen", 1)))
            basen[f"{kurz}:{k}"] = (x, r)
            varianten(praefix + k.replace(":", "_"), x, r, quelle=f"{kurz}:{k.split(':')[0]}")
            n_ok += 1
        except Exception as e:
            log(f"{praefix}{k}: {e}")
    return n_ok

N_NEU = lade_vertrag(BASIS_N, "neu/manifest_neu.json", "neu_", "neu") if BASIS_N else 0
N_SEC = lade_vertrag(BASIS, "sec/manifest_sec.json", "sec_", "sec")
log(f"Scout-Reihen {N_NEU}, SEC-Reihen {N_SEC}")

N_PAARE = 0
if os.path.exists(PAARE):
    for ln in open(PAARE, encoding="utf-8"):
        ln = ln.split("#", 1)[0].strip()
        if not ln:
            continue
        name, a, b, art = [t.strip() for t in ln.split(";")[:4]]
        if a not in basen or b not in basen:
            continue
        (xa, ra), (xb, rb) = basen[a], basen[b]
        j = pd.concat([xa, xb], axis=1, join="inner").dropna()
        if art == "logratio":
            j = j[(j.iloc[:, 0] > 0) & (j.iloc[:, 1] > 0)]
            s = np.log(j.iloc[:, 0]) - np.log(j.iloc[:, 1])
        else:
            s = j.iloc[:, 0] - j.iloc[:, 1]
        if len(s) >= 500:
            varianten(f"paar_{name}", s, ra + rb, quelle=f"paar:{name}"); N_PAARE += 1   # strengste Regel beider Seiten

try:
    btc_p = os.path.join(CACHE, "btc.csv")
    if not os.path.exists(btc_p):
        urllib.request.urlretrieve("https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/main/data/updates/btcusd_bitstamp_1min_latest.csv", btc_p)
    b = pd.read_csv(btc_p); b.index = pd.to_datetime(b.timestamp, unit="s")
    bd = b.close.resample("D").last().dropna()
    ind["btc_r1"] = (100 * bd.pct_change(), [("tag", LAG_SOFORT)]); ind["btc_r7"] = (100 * bd.pct_change(7), [("tag", LAG_SOFORT)])
except Exception as e:
    log("BTC übersprungen:", e)

# ================================================================== Ereignisse, Einstieg, Auswertung
def ereignisse(x, art, ist_ereignis=False):
    x = x.dropna()
    if ist_ereignis:
        return x.index[(x == 1).values]
    fenster_ = x.shift(1).rolling(252, min_periods=150)
    if art == "hoch":   m = x > fenster_.quantile(0.95)
    elif art == "tief": m = x < fenster_.quantile(0.05)
    else:
        dx = x.diff(); sd = dx.shift(1).rolling(252, min_periods=150).std()
        m = (dx > 3 * sd) if art == "sprung_auf" else (dx < -3 * sd)
    return x.index[m.fillna(False).values]

def einstieg(kal, tage, regeln):
    """Index des Einstiegstags je Ereignis nach allen Regeln (die späteste gilt). -1 = verworfen."""
    tage = pd.DatetimeIndex(tage)
    basis = kal.searchsorted(tage, side="right")
    pos = np.zeros(len(tage), dtype=int)
    for r in regeln:
        if r[0] == "tag":
            p = basis + (r[1] - 1)
        elif r[0] == "h10":          # Fed H.10: ab 2009 wöchentlich am Montag publiziert, Einstieg danach
            montag = tage + pd.to_timedelta(7 - tage.weekday, unit="D")
            p = np.where(tage < pd.Timestamp("2009-01-01"), basis + 1, kal.searchsorted(montag, side="right"))
        elif r[0] == "eia":          # EIA-Spotpreise: wöchentlich, Mittwoch der Folgewoche
            mittwoch = tage + pd.to_timedelta(7 - tage.weekday + 2, unit="D")
            p = kal.searchsorted(mittwoch, side="right")
        pos = np.maximum(pos, p)
    pos[basis < 1] = -1              # Ereignis vor Beginn des Kurskalenders: verworfen
    return pos

def entclustern(pos, abstand):
    out, letzte = [], -10**9
    for p in np.sort(pos):
        if p - letzte >= abstand:
            out.append(p); letzte = p
    return np.array(out, dtype=int)

def auswerten(fam, pos_roh, z, h, lo, mitte):
    f = FAM[fam]
    pos = entclustern(pos_roh, max(10, h))
    pos = pos[(pos >= lo) & (pos + f["rand"](h) < f["ende"])]
    werte = f["mr"][(z, h)][pos]; ok = ~np.isnan(werte); pos, werte = pos[ok], werte[ok]
    n = len(werte)
    if n < 10:
        return None
    ref = fenster(fam, z, h, lo, f["ende"])
    if ref is None:
        return None
    mu0, sd0 = ref; mu = werte.mean()
    sd = max(sd0, werte.std(ddof=1))
    t = (mu - mu0) / (sd / np.sqrt(n))
    t_klassisch = (mu - mu0) / (sd0 / np.sqrt(n))
    def th(w, r):
        if len(w) < 3 or r is None:
            return 0.0
        return (w.mean() - r[0]) / (max(r[1], w.std(ddof=1)) / np.sqrt(len(w)))
    t1 = th(werte[pos < mitte], fenster(fam, z, h, lo, mitte))
    t2 = th(werte[pos >= mitte], fenster(fam, z, h, mitte, f["ende"]))
    return dict(n=n, mu=mu, mu0=mu0, sd0=sd0, t=t, t_klassisch=t_klassisch, t1=t1, t2=t2, lo=lo,
                erste=str(f["kal"][pos[0]].date()), letzte=str(f["kal"][pos[-1]].date()), _pos=pos)

def suchlauf(placebo=False, seed=0):
    rng = np.random.default_rng(seed)
    zeilen = []
    for iname, (x, regeln) in ind.items():
        x = x[x.index <= STICHTAG].dropna()
        if len(x) < 160:
            continue
        start = x.index[0] if iname in EREIGNIS else x.index[min(150, len(x) - 1)]
        for art in (("hoch",) if iname in EREIGNIS else ("hoch", "tief", "sprung_auf", "sprung_ab")):
            tage = ereignisse(x, art, iname in EREIGNIS)
            if len(tage) < N_MIN:
                continue
            for fam, f in FAM.items():
                if fam == "L" and x.index[0] >= L_BEGINN_VOR:
                    continue
                kal = f["kal"]; lo = int(kal.searchsorted(start)); ende = f["ende"]
                if ende - lo <= 504:
                    continue
                pos = einstieg(kal, tage, regeln)
                pos = pos[(pos >= lo) & (pos < ende)]
                if len(pos) < 10:
                    continue
                if placebo:                   # Blockverschiebung innerhalb der Laufzeit: Häufung bleibt erhalten
                    span = ende - lo
                    off = int(rng.integers(252, span - 252))
                    pos = lo + (pos - lo + off) % span
                mitte = (lo + ende) // 2
                for z in f["ziele"]:
                    for h in HORIZONTE:
                        r = auswerten(fam, pos, z, h, lo, mitte)
                        if r:
                            zeilen.append(dict(familie=fam, indikator=iname, art=art, ziel=z, h=h, **r))
    return pd.DataFrame(zeilen)

def filtern(df, t_min):
    df = df.copy()
    rich = np.sign(df.t)
    df["f_t"] = df.t.abs() >= t_min
    df["f_kosten"] = rich * df.mu >= KOSTEN                     # F2 nach Verfassung: Mehrrendite gegenüber ACWI
    df["f_n"] = df.n >= N_MIN
    df["f_stabil"] = (np.sign(df.t1) == rich) & (np.sign(df.t2) == rich) & (df.t1.abs() >= T_HAELFTE) & (df.t2.abs() >= T_HAELFTE)
    df["alle"] = df.f_t & df.f_kosten & df.f_n & df.f_stabil
    df["vor"] = (df.t.abs() >= T_VOR) & df.f_kosten & df.f_n & df.f_stabil
    return df

def auswahl(df, t_min, rng):
    """Vollständige Auswahl: Filter, F5 (Bootstrap), ETF-Bestätigung für L. Gleich für echte und Placebo-Läufe."""
    df = filtern(df, t_min)
    ueber = df[df.vor & (df.t > 0)].sort_values("t", ascending=False).copy()
    pz, tb, tohne = [], [], []
    for _, r in ueber.iterrows():
        f = FAM[r.familie]; a = f["mr"][(r.ziel, int(r.h))][int(r.lo): f["ende"] - f["rand"](int(r.h))]
        a = a[~np.isnan(a)]
        sims = a[rng.integers(0, len(a), size=(N_F5, int(r.n)))].mean(axis=1)
        pz.append(float(((sims >= r.mu).sum() + 1) / (N_F5 + 1)))
        w = f["mr"][(r.ziel, int(r.h))][r._pos]; w = w[~np.isnan(w)]
        w2 = np.delete(w, np.argmax(w))                         # ohne das beste Einzelereignis
        tohne.append(float((w2.mean() - r.mu0) / (max(r.sd0, np.std(w2, ddof=1)) / np.sqrt(len(w2)))))
        t_etf = np.nan
        if r.familie == "L":
            etf = FF_ZIELE[r.ziel[3:]]
            m = df[(df.familie == "S") & (df.indikator == r.indikator) & (df.art == r.art) & (df.ziel == etf) & (df.h == r.h)]
            t_etf = float(m.t.iloc[0]) if len(m) else np.nan
        tb.append(t_etf)
    ueber["placebo_p"] = pz; ueber["t_bestaetigung_etf"] = tb; ueber["t_ohne_bestes"] = tohne
    kern = ueber.alle & (ueber.placebo_p < 0.01) if len(ueber) else ueber.alle
    best = (ueber.familie == "S") | ((np.sign(ueber.t_bestaetigung_etf) == 1) & (ueber.t_bestaetigung_etf >= T_BEST))
    return df, ueber, ueber[kern & best], ueber[kern & ~best]

SPALTEN = ["familie", "indikator", "art", "ziel", "h", "n", "mu", "mu0", "t", "t_klassisch", "t1", "t2"]

if __name__ == "__main__":
    t0 = time.time()
    log(f"Methode {METHODE} | Familien {', '.join(FAM)} | Ziele S {len(ZIELE)} | Indikatoren {len(ind)} | Placebo {N_PLACEBO}")
    roh = suchlauf()
    REG = register_laden()
    schluessel = (METHODE + "|" + roh.indikator + "|" + roh.art + "|" + roh.ziel + "|" + roh.h.astype(str)).tolist()
    NEU = set(schluessel) - REG
    KUM = KUM_VORHER + len(NEU)
    T_MIN = huerde_kumulativ(KUM)
    with open("hypothesen.txt.gz", "wb") as fh:
        fh.write(gzip.compress("\n".join(sorted(REG | set(schluessel))).encode("utf-8"), mtime=0))
    log(f"{len(roh)} Kandidaten, {len(NEU)} neu (Methode {METHODE}); kumuliert {KUM} -> Hürde t >= {T_MIN:.2f}")
    rng = np.random.default_rng(20260925)
    echt, ueber, bausteine, hinweise = auswahl(roh, T_MIN, rng)
    echt["neu"] = [k in NEU for k in schluessel]
    plac_bst, plac_alle, plac_vor = [], [], []
    for s in range(1, N_PLACEBO + 1):
        p_df, p_ue, p_b, _ = auswahl(suchlauf(placebo=True, seed=s), T_MIN, np.random.default_rng(1000 + s))
        plac_bst.append(int(len(p_b))); plac_alle.append(int((p_df.alle & (p_df.t > 0)).sum())); plac_vor.append(int((p_df.vor & (p_df.t > 0)).sum()))
        if s % 10 == 0 or s == N_PLACEBO:
            log(f"Placebo {s}/{N_PLACEBO}: Bausteine je Lauf bisher {plac_bst}")
    n_b = len(bausteine)
    p_lauf = (1 + sum(1 for x in plac_bst if x >= max(1, n_b))) / (N_PLACEBO + 1)
    fund = bool(n_b >= 1 and p_lauf <= 0.05)
    zus = {
        "methode": METHODE,
        "kandidaten": int(len(echt)), "kandidaten_neu": int(len(NEU)),
        "kandidaten_bekannt": int(len(set(schluessel)) - len(NEU)),
        "kandidaten_kumuliert": int(KUM), "huerde_t": round(float(T_MIN), 2),
        "familien": {fam: int((echt.familie == fam).sum()) for fam in FAM},
        "echt_alle_filter_positiv": int((echt.alle & (echt.t > 0)).sum()),
        "echt_vorstufe_positiv": int((echt.vor & (echt.t > 0)).sum()),
        "placebo_laeufe": N_PLACEBO,
        "placebo_bausteine_je_lauf": plac_bst,
        "placebo_alle_filter_je_lauf": plac_alle,
        "placebo_vorstufe_je_lauf": plac_vor,
        "p_lauf": round(p_lauf, 4),
        "fund": fund,
        "echt_mehr_als_staerkster_placebo": bool(n_b > max(plac_bst or [0])),
        "datenpruefung_verdachtstage": VERDACHT,
    }
    cols = SPALTEN + ["placebo_p", "t_bestaetigung_etf", "t_ohne_bestes"]
    zus["bausteine"] = bausteine[cols].round(4).to_dict("records")
    zus["langzeit_hinweise"] = hinweise[cols].round(4).to_dict("records")
    top = echt[(echt.t > 0) & (echt.n >= N_MIN)].sort_values("t", ascending=False)
    zus["staerkste_positive"] = top.head(10)[SPALTEN].round(3).to_dict("records")
    zus["staerkste_neue"] = top[top.neu].head(5)[SPALTEN].round(3).to_dict("records")
    echt["quelle"] = echt.indikator.map(quelle_von)
    jq = {}
    for q, g in echt.groupby("quelle"):
        pos_ = g[(g.t > 0) & (g.n >= N_MIN)]
        jq[q] = {"kandidaten": int(len(g)), "vorstufe_positiv": int((g.vor & (g.t > 0)).sum()),
                 "max_t": round(float(pos_.t.max()), 2) if len(pos_) else None}
    zus["je_quelle"] = dict(sorted(jq.items()))
    zus["indikatoren_n"] = len(ind)
    zus["indikatoren"] = sorted(ind)
    zus["ziele"] = {fam: f["ziele"] for fam, f in FAM.items()}
    zus["paare"] = N_PAARE
    zus["code_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()[:16]
    zus["dauer_min"] = round((time.time() - t0) / 60, 1)
    json.dump(zus, open("suchlauf_zusammenfassung.json", "w"), indent=1)
    ue = ueber.copy()
    ue["ereignisse"] = [";".join(str(FAM[r.familie]["kal"][p].date()) for p in r._pos) for _, r in ue.iterrows()]
    ue.drop(columns=["_pos"]).to_csv("suchlauf_ueberlebende.csv", index=False)
    echt.drop(columns=["_pos"]).to_csv("suchlauf_echt.csv.gz", index=False)
    log(json.dumps({k: v for k, v in zus.items() if k not in ("indikatoren", "je_quelle")}, indent=1))
