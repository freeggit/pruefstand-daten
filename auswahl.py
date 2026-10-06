"""Prüfstand – Auswahl des Finalisten und Vorprüfung der Öffnung (Verfassung V3.13, E27a/E27b/E27e).

Liest nur Discovery-Daten (über suchmaschine.py, Siegel durch Bau) und die Ergebnisse eines Suchlaufs. Das Programm
öffnet nichts, testet nichts auf versiegelten Daten und ändert keine Regel. Es beantwortet eine Frage: Gibt es heute
einen Finalisten, der die Vorprüfung der Öffnungsbedingung besteht? Über eine Öffnung entscheidet Reto.

Ablauf (mechanisch):
  1. Pool: Kandidaten der Suche (Familie S) mit Vorfilter, bestätigungsfähig (nicht explorativ), ohne Datenmangel,
     mindestens MIN_EREIGNISSE erwartete Ereignisse im Bestätigungszeitraum. Dazu bewertete Hypothesen der Klausur
     (Familie V) mit denselben Bedingungen.
  2. Rangfolge (E27b): Score aufsteigend, dann t absteigend, dann Kennung. Score der Suche = (k + 1) / (B + 1) an der
     ganzen Familie der Placebo-Läufe; Score der Klausur = p nach Holm in der Charge.
  3. Die besten K_MAX Regeln: der Rangfolge nach, je Grundreihe und je Ziel höchstens eine Regel.
  4. Finalist: die beste einzelne dieser Regeln, die die Vorprüfung besteht; sonst das kleinste Bündel der besten
     2, 3, ... K_MAX Regeln, das sie besteht; sonst keiner.
  5. Vorprüfung (E27a): Jahresschwankung der Strategie in der Discovery höchstens grenzwert(Jahre).
     grenzwert = ALTERNATIVE * Wurzel(Jahre) / (z(1 - NIVEAU) + z(STAERKE)); heute rund 5.1 Prozentpunkte.
Die volle Abnahme mit Welten (E27d) folgt nur für einen Finalisten, der die Vorprüfung besteht, und nur wenn Reto
eine Öffnung erwägt. Tests: python test_auswahl.py
"""
import datetime, json, math, os, sys
import numpy as np

K_MAX = 5                    # Bündel: 2 bis 5 Regeln (E27e)
NIVEAU = 0.05                # Fehlalarm der Bestätigung
STAERKE = 0.40               # Schwelle der Öffnung (E27a)
ALTERNATIVE = 3.0            # Prozentpunkte pro Jahr netto
MIN_EREIGNISSE = 10
BLOCK_SCHWANKUNG = 60        # Handelstage; Blocksummen fangen Häufung und Haltezeiten bis 20 Tage auf
BEGINN = datetime.date(2021, 2, 1)
SEED = 20261006              # fester Startwert der Welten (zweite Stufe)
W_ZENTRUM, W_NULL, W_STAERKE = 4000, 3000, 1500


def _z(p):
    """Quantil der Normalverteilung (Acklam), genau genug für den Grenzwert."""
    a = [-3.969683028665376e+01, 2.209460984245205e+02, -2.759285104469687e+02, 1.383577518672690e+02, -3.066479806614716e+01, 2.506628277459239e+00]
    b = [-5.447609879822406e+01, 1.615858368580409e+02, -1.556989798598866e+02, 6.680131188771972e+01, -1.328068155288572e+01]
    c = [-7.784894002430293e-03, -3.223964580411365e-01, -2.400758277161838e+00, -2.549732539343734e+00, 4.374664141464968e+00, 2.938163982698783e+00]
    d = [7.784695709041462e-03, 3.224671290700398e-01, 2.445134137142996e+00, 3.754408661907416e+00]
    if p < 0.02425:
        q = math.sqrt(-2 * math.log(p))
        return (((((c[0] * q + c[1]) * q + c[2]) * q + c[3]) * q + c[4]) * q + c[5]) / ((((d[0] * q + d[1]) * q + d[2]) * q + d[3]) * q + 1)
    if p > 1 - 0.02425:
        return -_z(1 - p)
    q = p - 0.5; r = q * q
    return (((((a[0] * r + a[1]) * r + a[2]) * r + a[3]) * r + a[4]) * r + a[5]) * q / (((((b[0] * r + b[1]) * r + b[2]) * r + b[3]) * r + b[4]) * r + 1)


def jahre_bestaetigung(oeffnungstag, beginn=BEGINN):
    """Länge des Bestätigungszeitraums in Jahren, nur aus dem Kalender (keine versiegelten Daten)."""
    return max(0.0, (oeffnungstag - beginn).days / 365.25)


def grenzwert(jahre, alternative=ALTERNATIVE, niveau=NIVEAU, staerke=STAERKE):
    """Höchste Jahresschwankung, bei der ein einseitiger Test auf dem Niveau die Alternative mit der Stärke erkennt."""
    if jahre <= 0:
        return 0.0
    return alternative * math.sqrt(jahre) / (_z(1 - niveau) + _z(staerke))


def staerke_naeherung(schwankung, jahre, alternative=ALTERNATIVE, niveau=NIVEAU):
    """Teststärke nach der Normalnäherung (Zusatzangabe; massgebend ist später die Abnahme mit Welten)."""
    if not np.isfinite(schwankung) or schwankung <= 0 or jahre <= 0:
        return 0.0
    return 0.5 * (1 + math.erf((alternative * math.sqrt(jahre) / schwankung - _z(1 - niveau)) / math.sqrt(2)))


def jahresschwankung(x, block=BLOCK_SCHWANKUNG):
    """Jahresschwankung eines täglichen Ertrags in Prozentpunkten aus Summen nicht überlappender Blöcke."""
    x = np.asarray(x, dtype=float)
    nb = len(x) // block
    if nb < 8 or not np.isfinite(x).all():
        return float("nan")
    s = x[:nb * block].reshape(nb, block).sum(axis=1)
    return float(s.std(ddof=1) * math.sqrt(252.0 / block))


def _r(v, stellen=3):
    """Runden; nicht endliche Werte werden zu None (strenges JSON)."""
    return round(float(v), stellen) if v is not None and np.isfinite(v) else None


def rho1(werte):
    """Zusammenhang aufeinanderfolgender Ereigniserträge, mindestens null (E27d)."""
    b = np.asarray(werte, dtype=float); b = b - b.mean()
    if len(b) < 4 or float((b * b).sum()) == 0.0:
        return 0.0
    return max(0.0, float((b[1:] * b[:-1]).sum() / (b * b).sum()))


def rangfolge(kandidaten):
    """kandidaten: Liste von dicts mit score, t, kennung. Gibt die sortierte Liste zurück (E27b)."""
    return sorted(kandidaten, key=lambda k: (k["score"], -k["t"], k["kennung"]))


def beste(rang, k_max=K_MAX):
    """Die besten k_max Regeln: der Rangfolge nach, je Grundreihe und je Ziel höchstens eine."""
    out, reihen, ziele = [], set(), set()
    for k in rang:
        if k["grundreihe"] in reihen or k["ziel"] in ziele:
            continue
        out.append(k); reihen.add(k["grundreihe"]); ziele.add(k["ziel"])
        if len(out) == k_max:
            break
    return out


def waehlen(top, schwankung_von, grenze, staerke_von=None, schwelle=STAERKE):
    """top: die besten Regeln in Rangfolge. schwankung_von(Liste von Regeln) -> Jahresschwankung des gleich gewichteten
    Bündels (Vorprüfung). staerke_von(Liste von Regeln) -> dict mit «staerke» aus Welten (zweite Stufe, nur nach bestandener
    Vorprüfung; None = nur Vorprüfung). Gibt (finalist, pruefungen) zurück; finalist ist eine Liste von Regeln oder None."""
    pruef = []
    faelle = [("einzeln", [k]) for k in top] + [(f"buendel_{m}", top[:m]) for m in range(2, len(top) + 1)]
    for art, regeln in faelle:                                # zuerst einzelne Regeln in Rangfolge, dann die kleinsten Bündel
        s = schwankung_von(regeln); ok = bool(np.isfinite(s) and s <= grenze)
        p = dict(art=art, regeln=[k["kennung"] for k in regeln], jahresschwankung_pp=s, vorpruefung=ok, bestanden=ok)
        if ok and staerke_von is not None:
            p["welten"] = staerke_von(regeln); p["bestanden"] = bool(p["welten"]["staerke"] >= schwelle)
        pruef.append(p)
        if p["bestanden"]:
            return regeln, pruef
    return None, pruef


def score_suche(t, plac_max):
    """(k + 1) / (B + 1): k = Placebo-Läufe, deren bestes t mindestens so hoch ist. Zähler und Nenner ungerundet."""
    pb = np.sort(np.asarray(plac_max, dtype=float))
    k = int(len(pb) - np.searchsorted(pb, t, side="left"))
    return k + 1, len(pb) + 1


# ====================================================================================================== Daten (Discovery)
def _lauf(echt_csv, zus_json, vorreg_dir, oeffnungstag, aus, mit_welten=False):
    import pandas as pd
    import suchmaschine as sm                    # lädt nur Daten bis zum Stichtag (Siegel durch Bau)
    import bestaetigung as bt
    kal = sm.FAM["S"]["kal"]; n0 = len(kal)

    def tag(df):
        d = df.reindex(kal); o = d.Open.values.astype(float); c = d.Close.values.astype(float)
        return c / o - 1, np.r_[np.nan, c[1:] / c[:-1] - 1]
    vor = np.asarray(kal < sm.ACWI_START); i0 = int(kal.searchsorted(sm.ACWI_START))
    ao, ac = tag(sm.acwi); ao = np.where(vor, np.nan, ao); ac = np.where(vor, np.nan, ac)
    if i0 < n0:
        ac[i0] = np.nan                          # kein Schluss->Schluss über den Beginn von ACWI
    bench = [[(1.0, ao, ac)], [(w,) + tuple(np.where(vor, x, np.nan) for x in tag(sm.kurse[t])) for t, w in sm.ERSATZ.items()]]
    tage = {}
    tab = {(e["indikator"], e["art"]): e for e in sm.ereignis_tabelle() if e["fam"] == "S"}

    def strategie(k):
        """Täglicher Netto-Mehrertrag der Regel in der Discovery, Fenster und Ereigniserträge."""
        e = tab[(k["indikator"], k["art"])]; z, h = k["ziel"], int(k["h"])
        if z not in tage:
            tage[z] = tag(sm.kurse[z])
        hi = min(e["hi"], n0)
        pos = sm.entclustern(e["pos"], max(10, h)); pos = pos[(pos >= e["lo"]) & (pos + h <= hi)]
        x, g = bt.tagesertrag(tage[z][0], tage[z][1], bench, None, pos, h, sm.KOSTEN)
        netto = np.array([x[p:p + h].sum() for p in g])
        return x, int(e["lo"]), int(hi), g, netto

    jahre = jahre_bestaetigung(oeffnungstag); grenze = grenzwert(jahre)
    zus = json.load(open(zus_json))
    plac = zus.get("placebo_bestes_t_je_lauf_roh") or zus["placebo_bestes_t_je_lauf"]     # ältere Läufe: nur gerundet
    plac_art = "ungerundet" if zus.get("placebo_bestes_t_je_lauf_roh") else "gerundet (Lauf vor V3.12)"
    d = pd.read_csv(echt_csv)
    if "explorativ" not in d:                                   # Läufe vor V3.12: Kennzeichen aus dem geltenden Code
        d["explorativ"] = d.indikator.map(sm.ist_explorativ)
    if "datenmangel" not in d:
        d["datenmangel"] = d.indikator.map(sm.hat_datenmangel)
    d = d[(d.familie == "S") & sm.vorfilter_a(d)].copy()
    n_vor = len(d)
    d = d[~d.explorativ.astype(bool) & ~d.datenmangel.astype(bool)]
    n_bf = len(d)
    d["je_jahr"] = d.n / ((d.hi - d.lo) / 252.0)
    d = d[d.je_jahr * jahre >= MIN_EREIGNISSE]
    kand = []
    for r in d.itertuples(index=False):
        za, ne = score_suche(float(r.t), plac)
        kand.append(dict(kennung=f"S|{r.indikator}|{r.art}|{r.ziel}|{int(r.h)}", familie="S", indikator=r.indikator, art=r.art,
                         ziel=r.ziel, h=int(r.h), t=float(r.t), n=int(r.n), mu=float(r.mu), je_jahr=float(r.je_jahr),
                         grundreihe=str(r.quelle), score=za / ne, score_zaehler=za, score_nenner=ne))
    n_v = 0
    if vorreg_dir and os.path.isdir(vorreg_dir):
        for f in sorted(os.listdir(vorreg_dir)):
            if not f.endswith(".json"):
                continue
            ch = json.load(open(os.path.join(vorreg_dir, f)))
            for hy in ch.get("hypothesen", []):
                if hy.get("status") != "bewertet" or hy.get("p_holm") is None:
                    continue
                ind, art, z, h = hy["schluessel"].split("|"); h = int(h)
                if (ind, art) not in tab or sm.ist_explorativ(ind) or sm.hat_datenmangel(ind):
                    continue
                if not (hy["t"] > 0 and hy["mu"] >= sm.KOSTEN and hy["n"] >= sm.N_MIN and min(hy["t1"], hy["t2"]) >= sm.T_HAELFTE):
                    continue
                e = tab[(ind, art)]; jj = hy["n"] / ((min(e["hi"], n0) - e["lo"]) / 252.0)
                if jj * jahre < MIN_EREIGNISSE:
                    continue
                n_v += 1
                kand.append(dict(kennung=f"V|{hy['id']}|{hy['schluessel']}", familie="V", indikator=ind, art=art, ziel=z, h=h,
                                 t=float(hy["t"]), n=int(hy["n"]), mu=float(hy["mu"]), je_jahr=float(jj),
                                 grundreihe=sm.quelle_von(ind), score=float(hy["p_holm"]), score_zaehler=None, score_nenner=None))
    rang = rangfolge(kand); top = beste(rang)
    cache = {}

    def strat(k):
        if k["kennung"] not in cache:
            cache[k["kennung"]] = strategie(k)
        return cache[k["kennung"]]

    def schwankung_von(regeln):
        teile = [strat(k) for k in regeln]
        lo = max(t[1] for t in teile); hi = min(t[2] for t in teile)
        return jahresschwankung(np.mean([t[0][lo:hi] for t in teile], axis=0))

    n_conf = int(round(jahre * 252)); block_w = 60

    def staerke_von(regeln):
        """Zweite Stufe (Entwicklungsgüte, keine Abnahme): Nullwelt «gesamt» aus gemeinsamen Ringblöcken der Discovery,
        Zentrum einmal bestimmt, Schwelle auf dem Raster geeicht, Teststärke bei der Alternative. Feste Startwerte."""
        teile = [strat(k) for k in regeln]; lo = max(t[1] for t in teile); hi = min(t[2] for t in teile); L = hi - lo
        hs = [int(k["h"]) for k in regeln]; zs = [k["ziel"] for k in regeln]
        evs = []
        for t in teile:
            ev = np.zeros(n0, bool); ev[t[3]] = True; evs.append(ev)
        nb = int(np.ceil(n_conf / block_w))

        def pfad(rng, zen, ziel_je):
            st = rng.integers(0, L, nb); idx = (lo + (st[:, None] + np.arange(block_w)[None, :]) % L).ravel()[:n_conf]
            bi = [[(g, o[idx], c[idx]) for g, o, c in korb] for korb in bench]
            X, ne = [], []
            for ev, z, h, ze, zj in zip(evs, zs, hs, zen, ziel_je):
                x, g = bt.tagesertrag(tage[z][0][idx], tage[z][1][idx], bi, None, np.where(ev[idx])[0], h, 0.0)
                for p in g:
                    x[p:p + h] += (zj - ze) / h
                X.append(x); ne.append(len(g))
            return np.mean(X, axis=0), X, ne
        m = len(regeln); seed = SEED + 1000 * m + sum(ord(c) for k in regeln for c in k["kennung"]) % 997
        rng = np.random.default_rng(seed); su = np.zeros(m); cn = np.zeros(m)
        for _ in range(W_ZENTRUM):
            _, X, ne = pfad(rng, [0.0] * m, [0.0] * m); su += [x.sum() for x in X]; cn += ne
        zen = su / np.maximum(cn, 1); f = np.maximum(cn / W_ZENTRUM / (n_conf / 252.0), 1e-9)

        def pw(npj, sd, n):
            rg = np.random.default_rng(sd); p = np.empty(n); ne_ = np.empty(n)
            for i in range(n):
                x, _, ne = pfad(rg, zen, [npj / fi for fi in f])
                p[i] = bt.p_wert(*bt.blocktest(x, rg, ziehungen=bt.ZIEHUNGEN)[:2]); ne_[i] = sum(ne)
            return p, ne_
        p0, _ = pw(0.0, seed + 1, W_NULL); c = bt.schwelle_diskret(p0, NIVEAU)
        p1, ne1 = pw(ALTERNATIVE, seed + 2, W_STAERKE)
        return dict(staerke=float((p1 <= c).mean()), staerke_nominal=float((p1 <= NIVEAU).mean()), schwelle=float(c),
                    fehlalarm_nominal=float((p0 <= NIVEAU).mean()), ereignisse_je_pfad=round(float(ne1.mean()), 1),
                    welten=dict(zentrum=W_ZENTRUM, null=W_NULL, staerke=W_STAERKE), tage=n_conf, startwert=int(seed),
                    art="Nullwelt gesamt, Ringblöcke 60 Tage, ohne Welt mit Abhängigkeit; Entwicklungsgüte")

    finalist, pruef = waehlen(top, schwankung_von, grenze, staerke_von if mit_welten else None)

    def karte(k):
        x, lo, hi, g, netto = strat(k)
        s = jahresschwankung(x[lo:hi])
        return dict(kennung=k["kennung"], familie=k["familie"], indikator=k["indikator"], art=k["art"], ziel=k["ziel"], h=k["h"],
                    score=k["score"], score_zaehler=k["score_zaehler"], score_nenner=k["score_nenner"], t=round(k["t"], 4),
                    ereignisse_discovery=int(len(g)), ereignisse_pro_jahr=round(k["je_jahr"], 2),
                    ereignisse_erwartet=round(k["je_jahr"] * jahre, 1), fenster=f"{kal[lo].date()} bis {kal[hi - 1].date()}",
                    jahresertrag_netto_discovery_pp=round(float(x[lo:hi].sum() / ((hi - lo) / 252.0)), 3),
                    jahresschwankung_pp=_r(s), staerke_naeherung=round(staerke_naeherung(s, jahre), 3),
                    abhaengigkeit_rho1=round(rho1(netto), 3))
    erg = dict(programm="auswahl.py", verfassung="V3.13", regel="E27a, E27b, E27e", erstellt_utc=datetime.datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ"),
               oeffnungstag=str(oeffnungstag), bestaetigung_beginn=str(BEGINN), jahre=round(jahre, 3),
               grenzwert_jahresschwankung_pp=round(grenze, 3),
               parameter=dict(niveau=NIVEAU, staerke=STAERKE, alternative_pp_pro_jahr=ALTERNATIVE, min_ereignisse=MIN_EREIGNISSE,
                              k_max=K_MAX, block_schwankung=BLOCK_SCHWANKUNG),
               suchlauf=dict(nr=zus.get("nr"), lauf_id=zus.get("lauf_id"), code_sha256=zus.get("code_sha256"), placebo_laeufe=len(plac), placebo_maxima=plac_art,
                             echt_csv=os.path.basename(echt_csv)),
               pool=dict(vorfilter=int(n_vor), bestaetigungsfaehig_ohne_datenmangel=int(n_bf), mit_genug_ereignissen=int(len(d)),
                         klausur=int(n_v), gesamt=len(kand)),
               beste=[karte(k) for k in top], pruefungen=[dict(p, jahresschwankung_pp=_r(p["jahresschwankung_pp"])) for p in pruef],
               finalist=None, bestanden=finalist is not None, stufen="Vorprüfung und Welten" if mit_welten else "nur Vorprüfung",
               hinweis="Die Vorprüfung ist eine Näherung aus der Discovery. Vor einer Öffnung folgen die Abnahme mit Welten (E27d), "
                       "die Verfügbarkeitsbelege (E30) und Retos Entscheid. Der Score ist eine Rangregel, keine Wahrscheinlichkeit.")
    if finalist is not None:
        teile = [strat(k) for k in finalist]; lo = max(t[1] for t in teile); hi = min(t[2] for t in teile)
        xb = np.mean([t[0][lo:hi] for t in teile], axis=0); s = jahresschwankung(xb)
        erg["finalist"] = dict(art="einzeln" if len(finalist) == 1 else f"buendel_{len(finalist)}", regeln=[k["kennung"] for k in finalist],
                               jahresschwankung_pp=round(s, 3), staerke_naeherung=round(staerke_naeherung(s, jahre), 3),
                               welten=next((p.get("welten") for p in pruef if p["bestanden"]), None),
                               jahresertrag_netto_discovery_pp=round(float(xb.sum() / ((hi - lo) / 252.0)), 3),
                               schlechtester_score=max(k["score"] for k in finalist),
                               abhaengigkeit_rho1=round(max(rho1(t[4]) for t in teile), 3))
    json.dump(erg, open(aus, "w"), ensure_ascii=False, indent=1, allow_nan=False)
    return erg


if __name__ == "__main__":
    echt = os.environ.get("PS_AUSWAHL_ECHT", "suchlauf_echt.csv.gz")
    zus_ = os.environ.get("PS_AUSWAHL_ZUS", "suchlauf_zusammenfassung.json")
    vdir = os.environ.get("PS_AUSWAHL_VORREG", "")
    tag_ = os.environ.get("PS_AUSWAHL_TAG")
    tag_ = datetime.date.fromisoformat(tag_) if tag_ else datetime.datetime.utcnow().date()
    e = _lauf(echt, zus_, vdir, tag_, os.environ.get("PS_AUSWAHL_AUS", "auswahl_e27.json"),
              mit_welten=os.environ.get("PS_AUSWAHL_WELTEN", "0") == "1")
    f = e["finalist"]
    print(f"Jahre {e['jahre']}, Grenzwert {e['grenzwert_jahresschwankung_pp']} pp; Pool {e['pool']['gesamt']}")
    for k in e["beste"]:
        print(f"  {k['kennung']}: Score {k['score']:.4f}, t {k['t']}, Schwankung {k['jahresschwankung_pp']} pp, Stärke s.W. {k['staerke_naeherung']}")
    for p in e["pruefungen"]:
        w = p.get("welten")
        print(f"  Prüfung {p['art']}: Schwankung {p['jahresschwankung_pp']} pp, Vorprüfung {p['vorpruefung']}" + (f", Welten: Stärke {w['staerke']:.3f}, Schwelle {w['schwelle']:.4f}" if w else "") + f", bestanden {p['bestanden']}")
    print("Finalist:", "keiner" if f is None else f"{f['art']} {f['regeln']} Schwankung {f['jahresschwankung_pp']} pp, Stärke s.W. {f['staerke_naeherung']}")
