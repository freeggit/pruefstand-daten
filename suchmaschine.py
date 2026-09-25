#!/usr/bin/env python3
"""Prüfstand – Suchmaschine (Suchraum, Verfassung V3.7, Methode M3).
Aufruf: python3 suchmaschine.py <basis main/data> [<basis claude/daten-energie/data>] [<basis claude/daten-neu/data>]
Umgebung: PS_CACHE, PS_KUM_VORHER, PS_REGISTER, PS_PLACEBO (Standard 20), PS_LANGZEIT, PS_PAARE,
          PS_BASIS_ENERGIE, PS_BASIS_NEU, PS_KALIBRIERUNG (1 = Trefferchance mit eingepflanztem Effekt messen, Standard 1).

Methode M3 (V3.7, 25.9.2026, zweite externe Gegenprüfung):
- Siegel durch Bau: jede Reihe (Kurse, Indikatoren) wird beim Laden am STICHTAG abgeschnitten, Ken French am
  31.12.2000. Kein Vorentscheid (Ereignisreihe, Mindestlänge, bereinigte Kurse) sieht spätere Werte.
- Verfügbarkeit: Tagesfrist je Quelle; Fed H.10 ab 2009 Montag nach der Beobachtungswoche + 2 Handelstage Puffer
  (Feiertage); EIA-Spotpreise nächster Mittwoch nach der Beobachtung + 1 Handelstag Puffer; Wetter 5 Handelstage.
  Paare: strengere Seite. Ereignisse vor Beginn des Kurskalenders verworfen.
- Keine Löschung verdächtiger Eröffnungskurse mehr (die Prüfung brauchte den späteren Schlusskurs). Stattdessen je
  Überlebendem: Ergebnis ohne Ereignisse an Verdachtstagen (t_ohne_verdacht); ein Baustein muss auch so halten.
- Temperaturnorm nur aus Vorjahren, nach Monat und Tag (29.2. = 28.2.).
- Referenz über die Laufzeit des Indikators (Beginn bis letzte Beobachtung); Hälften am festen Mittelpunkt, Fenster der
  ersten Hälfte enden vor dem Mittelpunkt; je Hälfte eigene Referenz.
- F1 robustes t; F2 Mehrrendite gegenüber ACWI >= 0.60 pp; F3 >= 30; F4 Hälften; F5 Rotationstest.
- Nullmodell: Rotation der Renditen. Alle Zielrenditen (Mehrrendite gegenüber ACWI) werden gemeinsam um denselben
  zufälligen Abstand (Vielfaches von 5 Handelstagen, mindestens 252) zirkulär verschoben; alle Indikatoren bleiben
  unverändert. So bleiben Zusammenhänge zwischen Indikatoren, zwischen Zielen und über die Zeit erhalten.
  Placebo-Läufe = ganze Auswahl auf rotierten Renditen. F5 = Rotationstest je Kandidat, p = (k+1)/(N+1).
- Fund nur, wenn Bausteine vorliegen und p_lauf <= 0.05. Fehlalarmrate = Anteil Placebo-Läufe mit >= 1 Baustein.
- Kalibrierung: in 40 zufällige echte Kandidaten wird ein bekannter Effekt eingepflanzt; gemessen wird, wie oft die
  unveränderte Auswahl ihn findet (Trefferchance).
- ETF-Bestätigung für Familie L: n >= 30, t >= 2 und Mehrrendite >= 0.60 pp auf dem zugeordneten ETF.
- Register: Schlüssel «M3|…». M3 ist eine Fehlerkorrektur von M2 (vor Sicht auf M3-Ergebnisse festgelegt): eine
  Hypothese, die unter M2 schon zählte, zählt nicht erneut.
"""
import gzip, hashlib, io, json, os, sys, time, urllib.request
import numpy as np, pandas as pd

METHODE, METHODE_VORHER = "M3", "M2"
STICHTAG = pd.Timestamp("2020-12-31")
L_ENDE = pd.Timestamp("2000-12-31")
HORIZONTE = [1, 5, 20]
T_BASIS, T_VOR, T_HAELFTE, T_BEST = 4.5, 3.5, 1.0, 2.0
KOSTEN = 0.60
N_MIN = 30
LAG_FRED, LAG_SOFORT, LAG_WETTER = 2, 1, 6
L_BEGINN_VOR = pd.Timestamp("1995-01-01")
KUM_VORHER = int(os.environ.get("PS_KUM_VORHER", "0"))
N_PLACEBO = int(os.environ.get("PS_PLACEBO", "20"))
N_F5 = 10000
KALIBRIERUNG = os.environ.get("PS_KALIBRIERUNG", "1") == "1"
LANGZEIT = os.environ.get("PS_LANGZEIT", "1") == "1"
PAARE = os.environ.get("PS_PAARE", os.path.join(os.path.dirname(os.path.abspath(__file__)), "paare.txt"))
FF_ZIELE = {"nodur": "xlp", "durbl": "xly", "manuf": "xli", "enrgy": "xle", "chems": "xlb", "buseq": "xlk",
            "telcm": "xlc", "utils": "xlu", "shops": "xly", "hlth": "xlv", "money": "xlf"}
H10 = {"fred:DEXSZUS", "fred:DTWEXBGS", "fred:DEXJPUS", "fred:DEXUSEU", "fred:DEXUSUK", "fred:DEXCAUS", "fred:DEXUSAL"}
H10_SCOUT = ("fred_usdjpy", "fred_fx_lang")
EIA = {"fred:DCOILWTICO", "fred:DHHNGSP", "fred:DCOILBRENTEU", "fred:DPROPANEMBTX"}
EIA_SCOUT = ("fred_brent", "fred_propane")
EFFEKT = {1: 0.8, 5: 1.5, 20: 3.0}            # Kalibrierung: eingepflanzter Effekt in pp je Haltedauer

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
    for q in [q for q in [os.environ.get("PS_REGISTER")] if q]:
        try:
            raw = open(q, "rb").read() if os.path.exists(q) else urllib.request.urlopen(q, timeout=120).read()
            reg = set(gzip.decompress(raw).decode("utf-8").split("\n")) - {""}
            log(f"Register: {len(reg)} Einträge"); return reg
        except Exception as e:
            log(f"Register nicht lesbar ({q}): {e}")
    return set()

def huerde_kumulativ(n_kum, alpha=0.05):
    from statistics import NormalDist
    return max(T_BASIS, NormalDist().inv_cdf(1 - alpha / 2 / max(n_kum, 1)))

def bis(x, tag=STICHTAG):
    return x[x.index <= tag]

# ================================================================== Familie S (alles abgeschnitten am STICHTAG)
man = json.load(open(lade("manifest.json")))
kurse, VERDACHT = {}, {}
for k, v in man["reihen"].items():
    if k.startswith("kurse:") and "fehler" not in v and v.get("granularitaet") == "1d":
        t = k.split(":", 1)[1]
        d = bis(pd.read_csv(lade(f"kurse/{t}_d.csv"), parse_dates=["Date"]).drop_duplicates("Date").set_index("Date").sort_index())
        if len(d) < 60:
            continue
        vor = d.Close.shift(1)
        verdacht = ((d.Open / vor - 1).abs() > 0.05) & ((d.Close / vor - 1).abs() < 0.02)
        VERDACHT[t] = set(d.index[verdacht])                   # nur Bericht, keine Löschung
        if "AdjClose" in d and d.AdjClose.notna().mean() > 0.99:
            f = (d.AdjClose / d.Close).astype(float)
            kurse[t] = pd.DataFrame({"Open": d.Open * f, "Close": d.AdjClose}).astype(float)
        else:
            kurse[t] = d[["Open", "Close"]].astype(float)
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

# Verdachtstage je Ziel als Kalenderindex (Ziel selbst oder Benchmark am Einstiegstag)
_bench_v = set(VERDACHT.get("acwi", set())) | {d for t in ERSATZ for d in VERDACHT.get(t, set()) if d < ACWI_START}
VERDACHT_POS = {z: set(KAL.get_indexer(sorted((VERDACHT.get(z, set()) | _bench_v) & set(KAL)))) for z in ZIELE}

FAM = {"S": dict(kal=KAL, ende=len(KAL), rand=lambda h: h - 1,
                 mr={(z, h): mehrrendite(z, h) for z in ZIELE for h in HORIZONTE}, ziele=ZIELE)}

# ================================================================== Familie L (Ken French, abgeschnitten am 31.12.2000)
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
    return bis(d.mask(d <= -99.99), L_ENDE)

def familie_l():
    dateien = [n for k, v in man["reihen"].items() if k.startswith("french:") for n in v.get("dateien", [])]
    ind_d = [n for n in dateien if "12_industry" in n.lower() and "daily" in n.lower()]
    fak_d = [n for n in dateien if "research_data_factors" in n.lower() and "daily" in n.lower() and "5_factors" not in n.lower()]
    if not ind_d or not fak_d:
        return None
    br = french_tag(ind_d[0]); fk = french_tag(fak_d[0])
    kal = br.index.intersection(fk.index)
    br, fk = br.reindex(kal), fk.reindex(kal)
    cm = np.log1p((fk["mkt_rf"] + fk["rf"]) / 100).cumsum().values
    mr = {}
    for z in FF_ZIELE:
        if z in br:
            cz = np.log1p(br[z] / 100).cumsum().values
            for h in HORIZONTE:
                i = np.arange(len(kal)); j = i + h; ok = j < len(kal)
                out = np.full(len(kal), np.nan)
                out[ok] = 100 * (np.expm1(cz[j[ok]] - cz[i[ok]]) - np.expm1(cm[j[ok]] - cm[i[ok]]))
                mr[("ff_" + z, h)] = out
    return dict(kal=kal, ende=len(kal), rand=lambda h: h, mr=mr, ziele=sorted({z for z, _ in mr}))

if LANGZEIT:
    try:
        fl = familie_l()
        if fl:
            FAM["L"] = fl
    except Exception as e:
        log(f"Langzeit übersprungen: {e}")

def praefix(mr):
    P = {}
    for key, a in mr.items():
        ok = ~np.isnan(a); v = np.where(ok, a, 0.0)
        P[key] = (np.concatenate([[0], np.cumsum(v)]), np.concatenate([[0], np.cumsum(v * v)]), np.concatenate([[0], np.cumsum(ok)]))
    return P

def fenster(P, f, z, h, lo, hi):
    """Mittel und Streuung der Mehrrendite für Einstiege lo.., deren Fenster vor hi (Index) endet."""
    hi = min(hi, f["ende"]) - f["rand"](h); lo = max(lo, 0)
    if hi - lo < 30:
        return None
    s, q, c = P[(z, h)]
    n = c[hi] - c[lo]
    if n < 30:
        return None
    m = (s[hi] - s[lo]) / n
    return m, np.sqrt(max((q[hi] - q[lo]) / n - m * m, 0.0) * n / (n - 1))

# ================================================================== Indikatoren (alle am STICHTAG abgeschnitten)
ind, EREIGNIS, QUELLE, basen = {}, set(), {}, {}

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
    x = bis(x).dropna()
    for suffix in ("_stand", "_d1", "_d5", "_d20", "_z252"):
        if quelle:
            QUELLE[n + suffix] = quelle
    if len(x) == 0:
        return
    if set(np.unique(x.values)) <= {0.0, 1.0}:
        ind[f"{n}_stand"] = (x, regeln); EREIGNIS.add(f"{n}_stand"); return
    m = x.rolling(252, min_periods=150)
    for suffix, s in (("_stand", x), ("_d1", x.diff()), ("_d5", x.diff(5)), ("_d20", x.diff(20)), ("_z252", (x - m.mean()) / m.std())):
        ind[n + suffix] = (s, regeln)

def fred(serie):
    f = pd.read_csv(lade(f"fred/{serie}.csv"), na_values=["."])
    f.columns = ["d", "v"]; f.d = pd.to_datetime(f.d)
    return bis(f.dropna().set_index("d").v.astype(float))

for s, v in man["reihen"].items():
    if s.startswith("fred:") and "fehler" not in v:
        x = fred(s.split(":", 1)[1])
        if len(x) < 500 or (x.index.to_series().diff().dt.days.median() > 3):
            continue
        r = regeln_fuer(s, LAG_FRED)
        basen[s] = (x, r)
        varianten(s.split(":", 1)[1], x, r, quelle=s)

def norm_vorjahre(s):
    """Tagesnorm nach Monat und Tag (29.2. = 28.2.), ±7 Tage geglättet, nur aus Vorjahren, mindestens 3 Vorjahre."""
    md = pd.Series(s.index.strftime("%m-%d"), index=s.index).replace("02-29", "02-28")
    tage = sorted(pd.date_range("2001-01-01", "2001-12-31").strftime("%m-%d"))
    df = pd.DataFrame({"v": s.values, "j": s.index.year, "md": md.values})
    tab = df.pivot_table(index="j", columns="md", values="v", aggfunc="mean").reindex(columns=tage)
    ext = pd.concat([tab.iloc[:, -7:], tab, tab.iloc[:, :7]], axis=1); ext.columns = range(ext.shape[1])
    sm = ext.T.rolling(15, center=True, min_periods=5).mean().T.iloc[:, 7:-7]; sm.columns = tage
    cs = sm.fillna(0).cumsum().shift(1); cn = sm.notna().cumsum().shift(1)
    norm = (cs / cn).where(cn >= 3)
    return pd.Series(norm.stack().reindex(list(zip(df.j, df.md))).values, index=s.index)

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
            for c in ("temperature_2m", "precipitation", "wind_speed_10m", "cloud_cover"):
                if c in d:
                    d[c] = pd.to_numeric(d[c], errors="coerce").astype(float)   # einheitlicher Typ (auch bei leeren Jahresdateien)
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            g = bis(d.set_index("t")).resample("D")
            tag = pd.DataFrame({"temp": g.temperature_2m.mean(), "regen": g.precipitation.sum(min_count=12),
                                "wind": g.wind_speed_10m.max(), "wolken": g.cloud_cover.mean()})
            for c in tag:
                s = tag[c].dropna()
                if c == "temp":
                    s = (s - norm_vorjahre(s)).dropna()
                ind[f"wetter_{name}_{c}"] = (s, [("tag", LAG_WETTER)])
        elif quelle == "energie" and name.startswith("preis"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            s = bis(d.set_index("t").preis_eur_mwh.astype(float).resample("D").mean().dropna())
            ind[f"strom_{name}"] = (s, [("tag", LAG_SOFORT)]); ind[f"strom_{name}_d1"] = (s.diff(), [("tag", LAG_SOFORT)])
        elif quelle == "energie" and name.startswith("erzeugung"):
            d["t"] = pd.to_datetime(d.zeit_utc.str.replace("Z", ""))
            tag = bis(d.set_index("t").apply(pd.to_numeric, errors="coerce")).resample("D").mean()
            for c in [c for c in tag.columns if any(w in c.lower() for w in ("wind", "solar", "load", "last"))]:
                ind[f"strom_{name}_{c.lower().replace(' ', '_')[:20]}"] = (tag[c].dropna(), [("tag", LAG_SOFORT)])
        elif quelle == "wiki":
            s = bis(d.set_index(pd.to_datetime(d.datum)).aufrufe.astype(float))
            ind[f"wiki_{name}_spike"] = (np.log1p(s) - np.log1p(s).rolling(28, min_periods=20).median(), [("tag", LAG_FRED)])

def lade_vertrag(basis, manifest_rel, praefix_, kurz):
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
            x = bis(x[~x.index.duplicated(keep="last")])
            if len(x) < 500 or x.index[0] > pd.Timestamp("2015-12-31") or x.index.to_series().diff().dt.days.median() > 3:
                continue
            r = regeln_fuer(f"{kurz}:{k}", 1 + int(v.get("verfuegbar_nach_tagen", 1)))
            basen[f"{kurz}:{k}"] = (x, r)
            varianten(praefix_ + k.replace(":", "_"), x, r, quelle=f"{kurz}:{k.split(':')[0]}")
            n_ok += 1
        except Exception as e:
            log(f"{praefix_}{k}: {e}")
    return n_ok

N_NEU = lade_vertrag(BASIS_N, "neu/manifest_neu.json", "neu_", "neu") if BASIS_N else 0
N_SEC = lade_vertrag(BASIS, "sec/manifest_sec.json", "sec_", "sec")

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
            varianten(f"paar_{name}", s, ra + rb, quelle=f"paar:{name}"); N_PAARE += 1

BTC_SHA = None
try:
    btc_p = os.path.join(CACHE, "btc.csv")
    if not os.path.exists(btc_p):
        urllib.request.urlretrieve("https://raw.githubusercontent.com/ff137/bitstamp-btcusd-minute-data/main/data/updates/btcusd_bitstamp_1min_latest.csv", btc_p)
    BTC_SHA = hashlib.sha256(open(btc_p, "rb").read()).hexdigest()[:16]
    b = pd.read_csv(btc_p); b.index = pd.to_datetime(b.timestamp, unit="s")
    bd = bis(b.close.resample("D").last().dropna())
    if len(bd):
        ind["btc_r1"] = (100 * bd.pct_change(), [("tag", LAG_SOFORT)]); ind["btc_r7"] = (100 * bd.pct_change(7), [("tag", LAG_SOFORT)])
except Exception as e:
    log("BTC übersprungen:", e)

# ================================================================== Ereignisse und Einstieg (einmal je Lauf)
def ereignisse(x, art, ist_ereignis=False):
    x = x.dropna()
    if ist_ereignis:
        return x.index[(x == 1).values]
    fw = x.shift(1).rolling(252, min_periods=150)
    if art == "hoch":   m = x > fw.quantile(0.95)
    elif art == "tief": m = x < fw.quantile(0.05)
    else:
        dx = x.diff(); sd = dx.shift(1).rolling(252, min_periods=150).std()
        m = (dx > 3 * sd) if art == "sprung_auf" else (dx < -3 * sd)
    return x.index[m.fillna(False).values]

def einstieg(kal, tage, regeln):
    tage = pd.DatetimeIndex(tage)
    basis = kal.searchsorted(tage, side="right")
    pos = np.zeros(len(tage), dtype=int)
    for r in regeln:
        if r[0] == "tag":
            p = basis + (r[1] - 1)
        elif r[0] == "h10":          # Montag nach der Beobachtungswoche, +2 Handelstage Puffer (Feiertage)
            montag = tage + pd.to_timedelta(7 - tage.weekday, unit="D")
            p = np.where(tage < pd.Timestamp("2009-01-01"), basis + 1, kal.searchsorted(montag, side="right") + 2)
        elif r[0] == "eia":          # nächster Mittwoch nach der Beobachtung, +1 Handelstag Puffer
            tage_bis = np.array((2 - tage.weekday) % 7)
            tage_bis[tage_bis == 0] = 7
            mittwoch = tage + pd.to_timedelta(tage_bis, unit="D")
            p = kal.searchsorted(mittwoch, side="right") + 1
        pos = np.maximum(pos, p)
    pos[basis < 1] = -1
    return pos

def entclustern(pos, abstand):
    out, letzte = [], -10**9
    for p in np.sort(pos):
        if p - letzte >= abstand:
            out.append(p); letzte = p
    return np.array(out, dtype=int)

def ereignis_tabelle():
    """Einmal je Lauf: je Indikator, Extremtyp und Familie die Einstiegsindizes, Laufzeit und Mittelpunkt."""
    tab = []
    for iname, (x, regeln) in ind.items():
        x = x.dropna()
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
                kal = f["kal"]; lo = int(kal.searchsorted(start))
                hi = min(f["ende"], int(kal.searchsorted(x.index[-1], side="right")) + 10)   # Laufzeit des Indikators
                if hi - lo <= 504:
                    continue
                pos = einstieg(kal, tage, regeln)
                pos = pos[(pos >= lo) & (pos < hi)]
                if len(pos) >= 10:
                    tab.append(dict(indikator=iname, art=art, fam=fam, pos=pos, lo=lo, hi=hi, mitte=(lo + hi) // 2))
    return tab

def auswerten(f, P, mr, e, z, h):
    pos = entclustern(e["pos"], max(10, h))
    pos = pos[pos + f["rand"](h) < e["hi"]]
    werte = mr[(z, h)][pos]; ok = ~np.isnan(werte); pos, werte = pos[ok], werte[ok]
    n = len(werte)
    if n < 10:
        return None
    ref = fenster(P, f, z, h, e["lo"], e["hi"])
    if ref is None:
        return None
    mu0, sd0 = ref; mu = werte.mean()
    t = (mu - mu0) / (max(sd0, werte.std(ddof=1)) / np.sqrt(n))
    def th(w, r):
        if len(w) < 3 or r is None:
            return 0.0
        return (w.mean() - r[0]) / (max(r[1], w.std(ddof=1)) / np.sqrt(len(w)))
    erst = pos + f["rand"](h) < e["mitte"]; zweit = pos >= e["mitte"]
    t1 = th(werte[erst], fenster(P, f, z, h, e["lo"], e["mitte"]))
    t2 = th(werte[zweit], fenster(P, f, z, h, e["mitte"], e["hi"]))
    return dict(n=n, mu=mu, mu0=mu0, sd0=sd0, t=t, t_klassisch=(mu - mu0) / (sd0 / np.sqrt(n)), t1=t1, t2=t2,
                lo=e["lo"], hi=e["hi"], _pos=pos)

def suchlauf(tab, mrs):
    """mrs: {fam: (mr, P)}. Gleiche Ereignisse, ggf. rotierte Renditen."""
    zeilen = []
    for e in tab:
        f = FAM[e["fam"]]; mr, P = mrs[e["fam"]]
        for z in f["ziele"]:
            for h in HORIZONTE:
                r = auswerten(f, P, mr, e, z, h)
                if r:
                    zeilen.append(dict(familie=e["fam"], indikator=e["indikator"], art=e["art"], ziel=z, h=h, **r))
    return pd.DataFrame(zeilen)

def rotiert(fam, rng):
    f = FAM[fam]; n = f["ende"]
    o = int(rng.integers(252 // 5, (n - 252) // 5)) * 5
    mr = {k: np.roll(a, o) for k, a in f["mr"].items()}
    return mr, praefix(mr), o

def filtern(df, t_min):
    df = df.copy()
    rich = np.sign(df.t)
    df["f_t"] = df.t.abs() >= t_min
    df["f_kosten"] = rich * df.mu >= KOSTEN
    df["f_n"] = df.n >= N_MIN
    df["f_stabil"] = (np.sign(df.t1) == rich) & (np.sign(df.t2) == rich) & (df.t1.abs() >= T_HAELFTE) & (df.t2.abs() >= T_HAELFTE)
    df["alle"] = df.f_t & df.f_kosten & df.f_n & df.f_stabil
    df["vor"] = (df.t.abs() >= T_VOR) & df.f_kosten & df.f_n & df.f_stabil
    return df

def f5_rotation(a, pos, mu, rng):
    n = len(a)
    offs = rng.integers(252 // 5, (n - 252) // 5, size=N_F5) * 5
    sims = np.nanmean(a[(pos[None, :] - offs[:, None]) % n], axis=1)
    return float((np.sum(sims >= mu) + 1) / (N_F5 + 1))

def auswahl(df, t_min, mrs, rng):
    df = filtern(df, t_min)
    ueber = df[df.vor & (df.t > 0)].sort_values("t", ascending=False).copy()
    pz, tb, tohne, tv, nv = [], [], [], [], []
    for _, r in ueber.iterrows():
        f = FAM[r.familie]; mr, _ = mrs[r.familie]; a = mr[(r.ziel, int(r.h))]; pos = r._pos
        pz.append(f5_rotation(a, pos, r.mu, rng))
        w = a[pos]
        w2 = np.delete(w, np.argmax(w))
        tohne.append(float((w2.mean() - r.mu0) / (max(r.sd0, np.std(w2, ddof=1)) / np.sqrt(len(w2)))))
        if r.familie == "S":
            v = np.array([p in VERDACHT_POS.get(r.ziel, set()) for p in pos])
            nv.append(int(v.sum()))
            wv = w[~v]
            tv.append(float((wv.mean() - r.mu0) / (max(r.sd0, np.std(wv, ddof=1)) / np.sqrt(len(wv)))) if len(wv) > 2 else np.nan)
        else:
            nv.append(0); tv.append(float(r.t))
        t_etf = np.nan
        if r.familie == "L":
            m = df[(df.familie == "S") & (df.indikator == r.indikator) & (df.art == r.art) & (df.ziel == FF_ZIELE[r.ziel[3:]]) & (df.h == r.h)]
            if len(m) and m.n.iloc[0] >= N_MIN and m.mu.iloc[0] >= KOSTEN:
                t_etf = float(m.t.iloc[0])
        tb.append(t_etf)
    ueber["placebo_p"] = pz; ueber["t_bestaetigung_etf"] = tb; ueber["t_ohne_bestes"] = tohne
    ueber["n_verdacht"] = nv; ueber["t_ohne_verdacht"] = tv; ueber["mu_netto"] = ueber.mu - KOSTEN
    if len(ueber) == 0:
        return df, ueber, ueber, ueber
    kern = ueber.alle & (ueber.placebo_p < 0.01) & ((ueber.n_verdacht == 0) | (ueber.t_ohne_verdacht >= t_min))
    best = (ueber.familie == "S") | (ueber.t_bestaetigung_etf >= T_BEST)
    return df, ueber, ueber[kern & best], ueber[kern & ~best]

SPALTEN = ["familie", "indikator", "art", "ziel", "h", "n", "mu", "mu_netto", "mu0", "t", "t_klassisch", "t1", "t2"]
ZUSATZ = ["placebo_p", "t_bestaetigung_etf", "t_ohne_bestes", "n_verdacht", "t_ohne_verdacht"]

if __name__ == "__main__":
    t0 = time.time()
    tab = ereignis_tabelle()
    echte = {fam: (f["mr"], praefix(f["mr"])) for fam, f in FAM.items()}
    log(f"Methode {METHODE} | Familien {', '.join(FAM)} | Ziele S {len(ZIELE)} | Indikatoren {len(ind)} | Ereignisreihen {len(tab)} | Placebo {N_PLACEBO}")
    roh = suchlauf(tab, echte)
    REG = register_laden()
    kern = (roh.indikator + "|" + roh.art + "|" + roh.ziel + "|" + roh.h.astype(str))
    schluessel = (METHODE + "|" + kern).tolist()
    vorher = (METHODE_VORHER + "|" + kern).tolist()
    NEU = {k for k, kv in zip(schluessel, vorher) if k not in REG and kv not in REG}
    KUM = KUM_VORHER + len(NEU)
    T_MIN = huerde_kumulativ(KUM)
    with open("hypothesen.txt.gz", "wb") as fh:
        fh.write(gzip.compress("\n".join(sorted(REG | set(schluessel))).encode("utf-8"), mtime=0))
    log(f"{len(roh)} Kandidaten, {len(NEU)} neu; kumuliert {KUM} -> Hürde t >= {T_MIN:.2f}")
    rng = np.random.default_rng(20260925)
    echt, ueber, bausteine, hinweise = auswahl(roh, T_MIN, echte, rng)
    echt["neu"] = [k in NEU for k in schluessel]
    plac_bst, plac_vor = [], []
    for s in range(1, N_PLACEBO + 1):
        prng = np.random.default_rng(1000 + s)
        mrs = {fam: rotiert(fam, prng)[:2] for fam in FAM}
        _, p_ue, p_b, _ = auswahl(suchlauf(tab, mrs), T_MIN, mrs, prng)
        plac_bst.append(int(len(p_b))); plac_vor.append(int(len(p_ue)))
        if s % 10 == 0 or s == N_PLACEBO:
            log(f"Placebo {s}/{N_PLACEBO}: Bausteine {sum(plac_bst)}, Läufe mit Baustein {sum(1 for x in plac_bst if x)}")
    n_b = len(bausteine)
    p_lauf = (1 + sum(1 for x in plac_bst if x >= n_b)) / (N_PLACEBO + 1) if n_b >= 1 else 1.0
    zus = {
        "methode": METHODE,
        "kandidaten": int(len(echt)), "kandidaten_neu": int(len(NEU)),
        "kandidaten_bekannt": int(len(set(schluessel)) - len(NEU)),
        "kandidaten_kumuliert": int(KUM), "huerde_t": round(float(T_MIN), 2),
        "familien": {fam: int((echt.familie == fam).sum()) for fam in FAM},
        "echt_alle_filter_positiv": int((echt.alle & (echt.t > 0)).sum()),
        "echt_vorstufe_positiv": int((echt.vor & (echt.t > 0)).sum()),
        "placebo_laeufe": N_PLACEBO, "placebo_art": "Rotation der Renditen (gemeinsam, Vielfache von 5 Handelstagen)",
        "placebo_bausteine_je_lauf": plac_bst, "placebo_vorstufe_je_lauf": plac_vor,
        "fehlalarmrate": round(sum(1 for x in plac_bst if x) / max(N_PLACEBO, 1), 4),
        "p_lauf": round(p_lauf, 4), "fund": bool(n_b >= 1 and p_lauf <= 0.05),
        "echt_mehr_als_staerkster_placebo": bool(n_b > max(plac_bst or [0])),
        "datenpruefung_verdachtstage": {t: sorted(str(d.date()) for d in v) for t, v in VERDACHT.items() if v},
    }
    zus["bausteine"] = bausteine[SPALTEN + ZUSATZ].round(4).to_dict("records")
    zus["langzeit_hinweise"] = hinweise[SPALTEN + ZUSATZ].round(4).to_dict("records")
    top = echt[(echt.t > 0) & (echt.n >= N_MIN)].sort_values("t", ascending=False)
    top = top.assign(mu_netto=top.mu - KOSTEN)
    zus["staerkste_positive"] = top.head(10)[SPALTEN].round(3).to_dict("records")
    zus["staerkste_neue"] = top[top.neu].head(5)[SPALTEN].round(3).to_dict("records")
    zus["familie_l_ereignisse"] = {"median_n": float(echt[echt.familie == "L"].n.median()) if "L" in FAM else None,
                                   "kandidaten_n_ab_30": int(((echt.familie == "L") & (echt.n >= N_MIN)).sum())}
    # Kalibrierung: bekannter Effekt in 40 zufällige echte S-Kandidaten mit n >= 40 eingepflanzt
    if KALIBRIERUNG:
        krng = np.random.default_rng(777)
        pool = echt[(echt.familie == "S") & (echt.n >= 40)]
        auswahl_k = pool.iloc[krng.choice(len(pool), size=min(40, len(pool)), replace=False)] if len(pool) else pool
        kal_erg = {}
        for faktor in (1.0, 2.0):
            treffer = 0
            for _, r in auswahl_k.iterrows():
                mr = dict(echte["S"][0]); a = mr[(r.ziel, int(r.h))].copy()
                a[r._pos] += faktor * EFFEKT[int(r.h)]
                mr[(r.ziel, int(r.h))] = a
                P = praefix({(r.ziel, int(r.h)): a})
                e = next(x for x in tab if x["indikator"] == r.indikator and x["art"] == r.art and x["fam"] == "S")
                rr = auswerten(FAM["S"], P, mr, e, r.ziel, int(r.h))
                if rr:
                    d1 = pd.DataFrame([dict(familie="S", indikator=r.indikator, art=r.art, ziel=r.ziel, h=int(r.h), **rr)])
                    _, _, b, _ = auswahl(d1, T_MIN, {"S": (mr, P)}, krng)
                    treffer += int(len(b) > 0)
            kal_erg[f"effekt_x{faktor:g}"] = {"eingepflanzt_pp": {str(h): round(faktor * v, 2) for h, v in EFFEKT.items()},
                                             "tests": int(len(auswahl_k)), "gefunden": treffer,
                                             "trefferchance": round(treffer / max(len(auswahl_k), 1), 3)}
        zus["kalibrierung"] = kal_erg
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
    zus["umgebung"] = {"numpy": np.__version__, "pandas": pd.__version__, "python": sys.version.split()[0], "btc_sha": BTC_SHA}
    zus["code_sha256"] = hashlib.sha256(open(os.path.abspath(__file__), "rb").read()).hexdigest()[:16]
    zus["dauer_min"] = round((time.time() - t0) / 60, 1)
    json.dump(zus, open("suchlauf_zusammenfassung.json", "w"), indent=1)
    ue = ueber.copy()
    ue["ereignisse"] = [";".join(str(FAM[r.familie]["kal"][p].date()) for p in r._pos) for _, r in ue.iterrows()]
    ue.drop(columns=["_pos"]).to_csv("suchlauf_ueberlebende.csv", index=False)
    echt.drop(columns=["_pos"]).round(4).to_csv("suchlauf_echt.csv.gz", index=False)
    log(json.dumps({k: v for k, v in zus.items() if k not in ("indikatoren", "je_quelle")}, indent=1))
