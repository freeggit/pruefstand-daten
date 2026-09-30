#!/usr/bin/env python3
"""Prüfstand – Analyse (V3.10, 30.9.2026; Stufe 1 und 4 freigegeben 29.9., «Analyse 50/50» freigegeben 30.9.): Diagnostik, keine Auswahl.

Stufe 1, Tiefenanalyse je Kandidat (die K_TOP besten positiven Kandidaten der Familie S eines Suchlaufs):
  Renditeverlauf um das Ereignis (Vorlauf −5 bis −1, Nachlauf 0 bis 20 Handelstage, Mehrrendite gegenüber ACWI),
  Zeitstabilität in Fünfjahresblöcken, Marktphase (SPY-Trend 60 Tage, VIX über oder unter Jahresmedian),
  Konzentration (Anteil der fünf besten Ereignisse, t ohne die drei besten), Empfindlichkeit der Schwelle
  (90% und 97.5% statt 95%; 2.5 und 3.5 statt 3 Standardabweichungen), verzögerter Einstieg (+1 Handelstag),
  Sektor-Kreuzvergleich und Horizontprofil aus dem vollständigen Suchergebnis, Beitrag in pp p.a. netto.
Stufe 4, Simulation des Zielkriteriums: hypothetischer Regelsatz aus den K besten Kandidaten (Rangfolge nach t,
  keine Überlappung, Kosten je Wechsel) als Papierstrategie gegen ACWI über die ganze Discovery; dieselbe
  Konstruktion auf N_PLAC_SIM Placebo-Suchläufen (rotierte Renditen) als Massstab für das Aggregat-Signal;
  Bedarfstabelle (wie viele Wechsel je Jahr welcher Stärke für 3 pp p.a. netto).

Siegel: rechnet ausschliesslich über suchmaschine.py; jede Reihe ist dort am STICHTAG abgeschnitten. Kein Filter,
keine Hürde; Schwellenvarianten sind Robustheitsbericht, nie neue Hypothesen (L1).
Aufruf in der Action: python3 analyse.py            (liest _lernen/index.json, schreibt _lernen/suche/S####_analyse.json)
Von Hand: python3 analyse.py --alle <S####_alle.csv.gz> --out <datei.json> [--kandidat "indikator|art|ziel|h" ...]
Umgebung wie suchmaschine.py; Basis wird wie in suche_lauf.py aus dem Repo abgeleitet, wenn kein Argument angegeben ist.
"""
import json, os, sys, time
import numpy as np, pandas as pd

def log(*a):
    print(*a, file=sys.stderr, flush=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
K_TOP = int(os.environ.get("PS_ANALYSE_K", "50"))
N_PLAC_SIM = int(os.environ.get("PS_ANALYSE_PLACEBO", "50"))
KMAX, VORLAUF = 20, 5
BLOECKE = [(2001, 2005), (2006, 2010), (2011, 2015), (2016, 2020)]

# ---------------------------------------------------------------- Argumente, dann Suchmaschine laden (versiegelt)
args = sys.argv[1:]
def opt(name, default=None, mehrfach=False):
    out = []
    while name in args:
        i = args.index(name); out.append(args[i + 1]); del args[i:i + 2]
    return out if mehrfach else (out[-1] if out else default)
ALLE, OUT, KANDIDATEN = opt("--alle"), opt("--out"), opt("--kandidat", mehrfach=True)
basis = args[0] if args else "file://" + os.path.join(ROOT, "data")
sys.argv = [sys.argv[0], basis]
for pfad, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
    if var not in os.environ and os.path.isdir(os.path.join(ROOT, pfad, "data")):
        os.environ[var] = "file://" + os.path.join(ROOT, pfad, "data")
sys.path.insert(0, ROOT)
t0 = time.time()
import suchmaschine as sm  # noqa: E402  (lädt alle Reihen, abgeschnitten am STICHTAG)

KAL, N = sm.KAL, len(sm.KAL)
F = sm.FAM["S"]; MR = F["mr"]; P_S = sm.praefix(MR)
KOSTEN, N_MIN = sm.KOSTEN, sm.N_MIN

def arr(df):
    d = df.reindex(KAL); return d.Open.values.astype(float), d.Close.values.astype(float)
Z = {z: arr(sm.kurse[z]) for z in sm.ZIELE}
ao, ac = arr(sm.acwi); so, sc = arr(sm.kurse["spy"]); eo, ec = arr(sm.kurse["efa"])
A_START = int(KAL.searchsorted(sm.ACWI_START))
W_SPY, W_EFA = sm.ERSATZ["spy"], sm.ERSATZ["efa"]

def bench(p0, p1, von_open=True):
    """Benchmark-Rendite von Tag p0 (Open oder Close) bis Close p1; vor ACWI-Start Ersatz 55% SPY + 45% EFA."""
    a0 = ao if von_open else ac; s0 = so if von_open else sc; e0 = eo if von_open else ec
    r = np.where(p0 >= A_START, ac[p1] / a0[p0] - 1, W_SPY * (sc[p1] / s0[p0] - 1) + W_EFA * (ec[p1] / e0[p0] - 1))
    r = np.where((p0 < A_START) & (p1 >= A_START), np.nan, r)
    return r

def ex_pfad(z, pos):
    """Mehrrendite in pp: Vorlauf (Close p−6 bis Close p+k, k=−5..−1) und Nachlauf (Open p bis Close p+k, k=0..KMAX)."""
    zo, zc = Z[z]; pos = np.asarray(pos)
    vor = {}
    for k in range(-VORLAUF, 0):
        p0, p1 = pos - VORLAUF - 1, pos + k; ok = p0 >= 0
        v = np.full(len(pos), np.nan); v[ok] = 100 * ((zc[p1[ok]] / zc[p0[ok]] - 1) - bench(p0[ok], p1[ok], von_open=False))
        vor[k] = v
    nach = {}
    for k in range(0, KMAX + 1):
        p1 = pos + k; ok = p1 < N
        v = np.full(len(pos), np.nan); v[ok] = 100 * ((zc[p1[ok]] / zo[pos[ok]] - 1) - bench(pos[ok], p1[ok]))
        nach[k] = v
    return vor, nach

def tstat(w):
    w = w[~np.isnan(w)]
    return (float(w.mean()), float(w.mean() / (w.std(ddof=1) / np.sqrt(len(w)))) if len(w) >= 3 and w.std(ddof=1) > 0 else np.nan, int(len(w)))

def rund(x, n=3):
    if x is None: return None
    if isinstance(x, (float, np.floating)): return None if np.isnan(x) else round(float(x), n)
    return x

# ---------------------------------------------------------------- Ereignistabelle und Positionen wie in der Suche
TAB = sm.ereignis_tabelle()
TAB_S = {(e["indikator"], e["art"]): e for e in TAB if e["fam"] == "S"}

def positionen(ind, art, h):
    e = TAB_S.get((ind, art))
    if e is None:
        return None, None
    pos = sm.entclustern(e["pos"], max(10, h)); pos = pos[pos + F["rand"](h) < e["hi"]]
    return e, pos

def ereignisse_variante(x, art, q=None, mult=None):
    x = x.dropna(); fw = x.shift(1).rolling(252, min_periods=150)
    if art == "hoch":   m = x > fw.quantile(q)
    elif art == "tief": m = x < fw.quantile(1 - q)
    else:
        dx = x.diff(); sd = dx.shift(1).rolling(252, min_periods=150).std()
        m = (dx > mult * sd) if art == "sprung_auf" else (dx < -mult * sd)
    return x.index[m.fillna(False).values]

# Marktphasen-Reihen (nur Vergangenheit je Tag)
spy_trend = pd.Series(sc).pct_change(60).shift(1).values                       # SPY-Rendite der 60 Vortage
vix = None
if "VIXCLS_stand" in sm.ind:
    v = sm.ind["VIXCLS_stand"][0].reindex(KAL).ffill()
    vix = (v > v.rolling(252, min_periods=150).median()).shift(1).values      # über dem Jahresmedian, Vortag

def profil(ind, art, z, h, alle):
    e, pos = positionen(ind, art, h)
    if e is None or pos is None or len(pos) < 5:
        return {"indikator": ind, "art": art, "ziel": z, "h": h, "fehler": "keine Ereignistabelle oder zu wenige Ereignisse"}
    a = MR[(z, h)]; w = a[pos]; ok = ~np.isnan(w); pos, w = pos[ok], w[ok]
    r = sm.auswerten(F, P_S, MR, e, z, h)
    if r is None:
        return {"indikator": ind, "art": art, "ziel": z, "h": h, "fehler": "keine Referenz"}
    mu0, sd0 = r["mu0"], r["sd0"]
    def t_ref(v):
        v = v[~np.isnan(v)]
        return (float(v.mean()), float((v.mean() - mu0) / (max(sd0, v.std(ddof=1)) / np.sqrt(len(v)))), int(len(v))) if len(v) >= 3 else (np.nan, np.nan, int(len(v)))
    out = {"indikator": ind, "art": art, "ziel": z, "h": h, "n": int(r["n"]), "mu": rund(r["mu"]), "mu0": rund(mu0), "t": rund(r["t"]),
           "t1": rund(r["t1"]), "t2": rund(r["t2"]), "mu_netto": rund(r["mu"] - KOSTEN),
           "lo": str(KAL[e["lo"]].date()), "hi": str(KAL[min(e["hi"], N) - 1].date())}
    jahre = (e["hi"] - e["lo"]) / 252
    out["ereignisse_pa"] = rund(len(w) / jahre); out["beitrag_pp_pa_netto"] = rund(len(w) / jahre * (r["mu"] - KOSTEN))
    # Verlauf
    vor, nach = ex_pfad(z, pos)
    out["verlauf"] = {"vorlauf": {str(k): [rund(x) for x in tstat(v)[:2]] for k, v in vor.items()},
                      "nachlauf": {str(k): [rund(x) for x in tstat(v)[:2]] for k, v in nach.items()}}
    pfad = [tstat(nach[k])[0] for k in range(KMAX + 1)]
    spitze = int(np.nanargmax(pfad)); out["verlauf"]["spitze_tag"] = spitze; out["verlauf"]["spitze_pp"] = rund(pfad[spitze])
    out["verlauf"]["tag0_anteil"] = rund(pfad[0] / pfad[h - 1]) if pfad[h - 1] and pfad[h - 1] > 0 else None
    out["verlauf"]["nach_h_bis_20"] = rund(pfad[KMAX] - pfad[h - 1])
    # Zeitstabilität
    jahr = np.array([d.year for d in KAL[pos]])
    out["bloecke"] = {}
    for a_, b_ in BLOECKE:
        m = (jahr >= a_) & (jahr <= b_)
        if m.sum() >= 5:
            mu_b, t_b, n_b = t_ref(w[m]); out["bloecke"][f"{a_}-{b_}"] = {"n": n_b, "mu": rund(mu_b), "t": rund(t_b)}
    # Marktphase
    tr = spy_trend[pos]; out["marktphase"] = {}
    for name, m in (("spy_trend_positiv", tr > 0), ("spy_trend_negativ", tr <= 0)):
        m = m & ~np.isnan(tr)
        if m.sum() >= 5:
            mu_b, t_b, n_b = t_ref(w[m]); out["marktphase"][name] = {"n": n_b, "mu": rund(mu_b), "t": rund(t_b)}
    if vix is not None:
        vv = vix[pos]
        for name, m in (("vix_hoch", vv == 1), ("vix_tief", vv == 0)):
            m = m & ~np.isnan(vv.astype(float))
            if m.sum() >= 5:
                mu_b, t_b, n_b = t_ref(w[m]); out["marktphase"][name] = {"n": n_b, "mu": rund(mu_b), "t": rund(t_b)}
    # Konzentration
    ws = np.sort(w)[::-1]
    out["konzentration"] = {"anteil_top5": rund(ws[:5].sum() / ws.sum()) if ws.sum() > 0 else None,
                            "t_ohne_top3": rund(t_ref(ws[3:])[1]), "t_ohne_top1": rund(t_ref(ws[1:])[1]),
                            "median_pp": rund(float(np.median(w))), "anteil_positiv": rund(float((w > 0).mean()))}
    # Verdachtstage
    v = np.array([p in sm.VERDACHT_POS.get(z, set()) for p in pos])
    out["n_verdacht"] = int(v.sum()); out["t_ohne_verdacht"] = rund(t_ref(w[~v])[1]) if (~v).sum() >= 3 else None
    # Schwellen-Empfindlichkeit (nur Bericht)
    x, regeln = sm.ind[ind]
    out["schwellen"] = {}
    if ind not in sm.EREIGNIS:
        var = [("q90", dict(q=0.90)), ("q975", dict(q=0.975))] if art in ("hoch", "tief") else [("sd2.5", dict(mult=2.5)), ("sd3.5", dict(mult=3.5))]
        for name, kw in var:
            tage = ereignisse_variante(x, art, **kw)
            p2 = sm.einstieg(KAL, tage, regeln); p2 = p2[(p2 >= e["lo"]) & (p2 < e["hi"])]
            p2 = sm.entclustern(p2, max(10, h)); p2 = p2[p2 + F["rand"](h) < e["hi"]]
            w2 = a[p2]; mu2, t2_, n2 = t_ref(w2)
            out["schwellen"][name] = {"n": n2, "mu": rund(mu2), "t": rund(t2_)}
    # verzögerter Einstieg
    p3 = pos + 1; p3 = p3[p3 + F["rand"](h) < e["hi"]]; mu3, t3, n3 = t_ref(a[p3])
    out["verzoegert_1_tag"] = {"n": n3, "mu": rund(mu3), "t": rund(t3)}
    # Kreuzvergleich und Horizonte aus dem Suchergebnis
    if alle is not None:
        k = alle[(alle.familie == "S") & (alle.indikator == ind) & (alle.art == art) & (alle.h == h)].sort_values("t", ascending=False)
        out["kreuz_ziele"] = [{"ziel": r_.ziel, "t": rund(r_.t), "mu": rund(r_.mu)} for r_ in k.head(8).itertuples()]
        out["rang_ziel"] = int((k.ziel.tolist().index(z) + 1)) if z in k.ziel.tolist() else None
        hh = alle[(alle.familie == "S") & (alle.indikator == ind) & (alle.art == art) & (alle.ziel == z)]
        out["horizonte"] = {str(int(r_.h)): {"t": rund(r_.t), "mu": rund(r_.mu), "n": int(r_.n)} for r_ in hh.itertuples()}
    return out

# ---------------------------------------------------------------- Stufe 4: Simulation
def top_k(df, k):
    d = df[(df.familie == "S") & (df.t > 0) & (df.n >= N_MIN) & (df.mu >= KOSTEN)]
    return d.sort_values("t", ascending=False).head(k)

def strategie(kand, mr):
    """Papierstrategie: Rangfolge nach t, keine Überlappung, Kosten je Wechsel. kand: DataFrame mit indikator, art, ziel, h, t."""
    ereignisse = []
    for rang, r in enumerate(kand.itertuples()):
        e, pos = positionen(r.indikator, r.art, int(r.h))
        if pos is None:
            continue
        for p in pos:
            ereignisse.append((int(p), rang, r.ziel, int(r.h)))
    ereignisse.sort()
    frei, summe, wechsel, kurve, ende = 0, 0.0, 0, np.zeros(N), 0
    for p, rang, z, h in ereignisse:
        if p < frei:
            continue
        x = mr[(z, h)][p]
        if np.isnan(x):
            continue
        summe += x - KOSTEN; wechsel += 1; frei = p + h; ende = min(p + h - 1, N - 1)
        kurve[ende] += x - KOSTEN
    kum = np.cumsum(kurve); dd = float(np.max(np.maximum.accumulate(kum) - kum)) if N else 0.0
    jahre = N / 252
    return {"netto_pp_pa": rund(summe / jahre), "brutto_pp_pa": rund((summe + wechsel * KOSTEN) / jahre), "wechsel_pa": rund(wechsel / jahre),
            "wechsel": wechsel, "max_rueckstand_pp": rund(dd), "jahre": rund(jahre, 1)}

def simulation(alle, tab):
    out = {"kosten_pp_je_wechsel": KOSTEN, "k": {}, "placebo": []}
    for k in (5, 10, 20):
        out["k"][str(k)] = strategie(top_k(alle, k), MR)
    for s in range(1, N_PLAC_SIM + 1):
        prng = np.random.default_rng(3000 + s)
        mrs = {fam: sm.rotiert(fam, prng)[:2] for fam in sm.FAM}
        d = sm.suchlauf(tab, mrs)
        out["placebo"].append({str(k): strategie(top_k(d, k), mrs["S"][0]) for k in (5, 10, 20)})
    for k in (5, 10, 20):
        pl = [p[str(k)]["netto_pp_pa"] for p in out["placebo"]]
        out["k"][str(k)]["placebo_netto_pp_pa"] = {"median": rund(float(np.median(pl))), "max": rund(float(np.max(pl))), "min": rund(float(np.min(pl)))}
        out["k"][str(k)]["echt_ueber_allen_placebos"] = bool(out["k"][str(k)]["netto_pp_pa"] > max(pl))
    out["bedarf_fuer_3pp_pa"] = [{"netto_pp_je_wechsel": e, "wechsel_pa_noetig": rund(3.0 / e, 1), "ereignisse_in_20_jahren": int(round(20 * 3.0 / e))}
                                 for e in (0.5, 1.0, 1.5, 2.0, 3.0)]
    return out

# ---------------------------------------------------------------- Hauptteil
if __name__ == "__main__":
    lernen = os.path.join(ROOT, "_lernen"); ip = os.path.join(lernen, "index.json"); nr = None
    if ALLE is None:
        if not os.path.exists(ip):
            log("kein _lernen/index.json und kein --alle: nichts zu tun"); sys.exit(0)
        index = json.load(open(ip, encoding="utf-8"))
        letzte = [s for s in index["suchlaeufe"] if s.get("datei")][-1]
        nr = int(letzte["nr"]); name = f"S{nr:04d}"
        OUT = OUT or os.path.join(lernen, "suche", f"{name}_analyse.json")
        if os.path.exists(OUT):
            log(f"{name}_analyse.json besteht schon: nichts zu tun"); sys.exit(0)
        lauf = os.environ.get("PS_LAUF", "/tmp/lauf")
        ALLE = os.path.join(lauf, "suchlauf_echt.csv.gz") if os.path.exists(os.path.join(lauf, "suchlauf_echt.csv.gz")) else os.path.join(lernen, "suche", f"{name}_alle.csv.gz")
    alle = pd.read_csv(ALLE)
    log(f"Analyse: {len(alle)} Kandidaten aus {ALLE}; Laden {(time.time() - t0) / 60:.1f} min")
    kand = [tuple(k.split("|")) for k in KANDIDATEN] if KANDIDATEN else [(r.indikator, r.art, r.ziel, int(r.h)) for r in top_k(alle, K_TOP).itertuples()]
    profile = [profil(i, a, z, int(h), alle) for i, a, z, h in kand]
    log(f"{len(profile)} Profile; {(time.time() - t0) / 60:.1f} min")
    erg = {"lauf": nr, "methode": sm.METHODE, "stichtag": str(sm.STICHTAG.date()), "kalender": [str(KAL[0].date()), str(KAL[-1].date())],
           "k_top": K_TOP, "kosten_pp_je_wechsel": KOSTEN, "profile": profile}
    if not KANDIDATEN:
        erg["simulation"] = simulation(alle, TAB)
        log(f"Simulation fertig; {(time.time() - t0) / 60:.1f} min")
    erg["dauer_min"] = round((time.time() - t0) / 60, 1)
    if OUT:
        os.makedirs(os.path.dirname(OUT), exist_ok=True)
        json.dump(erg, open(OUT, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        log(f"geschrieben: {OUT}")
    else:
        print(json.dumps(erg, ensure_ascii=False, indent=1))
