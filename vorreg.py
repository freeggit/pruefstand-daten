#!/usr/bin/env python3
"""Prüfstand – vorregistrierte Hypothesen, Familie V (Verfassung V3.10, E23; von Reto freigegeben am 30.9.2026:
«Analyse auf claude-opus-5-5, V3.10 mit Stufe 2 und 3, Analyse 50/50 wie vorgeschlagen»).

Liest alle Chargen vorregistrierung/<JJJJ-MM-TT>.json auf main und bewertet jede Hypothese genau einmal
(Ergebnis auf claude/lernen: vorreg/<charge>.json). Eine Charge hat höchstens 10 Hypothesen:
  {charge, registriert_utc, verfassung, autor, hypothesen: [{id, indikator, art, ziel, h, erwartung "positiv",
   mechanismus, literatur}]}
Prüfungen je Hypothese (ohne Blick auf ihr Ergebnis):
  gueltig      Indikatorname, Art, Ziel (Familie S) und Haltedauer (1, 5, 20) existieren; erwartung «positiv».
  kontaminiert Die Hypothese (indikator|art|ziel|h) stand vor dem Registrierdatum in einer Bestenliste eines
               Suchlaufs oder einer Analyse (S####.json staerkste_*, route_c_stufe1, S####_ueberlebende.csv,
               S####_analyse.json). Solche Hypothesen sind gesehen und werden nicht bewertet.
  wartet       Indikator noch nicht im Suchraum (neue Quelle im Aufbau); höchstens 60 Tage, dann «verfallen».
Bewertung (wie Familie S, Siegel durch Bau über suchmaschine.py): n, Mehrrendite mu gegenüber ACWI, robustes t,
Hälften t1/t2, p aus dem Rotationstest F5 (10'000 Rotationen, einseitig), Holm-Korrektur über die bewerteten
Hypothesen der Charge (familienweise 5%), t ohne Ereignisse an Verdachtstagen.
V-Baustein: p_holm <= 0.05, mu >= KOSTEN (0.88 pp), n >= 30, t1 und t2 gleichgerichtet und je >= 1,
t_ohne_verdacht >= 2. Chargen-Fehlalarm: dieselbe Auswertung auf 200 gemeinsamen Rotationen aller Renditen
(Anteil Rotationen mit mindestens einem V-Baustein) wird berichtet.
Ein V-Baustein ist ein Fund im Sinne der Verfassung: Fixierung durch Reto nötig, Siegel bleibt zu.
"""
import glob, gzip, io, json, os, sys, time
import numpy as np, pandas as pd

def log(*a):
    print(*a, file=sys.stderr, flush=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.path.join(ROOT, "_lernen")
MAX_JE_CHARGE, WARTEFRIST_TAGE, N_ROT_CHARGE, ALPHA = 10, 60, 200, 0.05
basis = "file://" + os.path.join(ROOT, "data")
sys.argv = [sys.argv[0], basis]
for pfad, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
    if var not in os.environ and os.path.isdir(os.path.join(ROOT, pfad, "data")):
        os.environ[var] = "file://" + os.path.join(ROOT, pfad, "data")

chargen = sorted(glob.glob(os.path.join(ROOT, "vorregistrierung", "*.json")))
if not chargen:
    log("keine Chargen unter vorregistrierung/"); sys.exit(0)
os.makedirs(os.path.join(LERNEN, "vorreg"), exist_ok=True)
offen = []
for c in chargen:
    name = os.path.splitext(os.path.basename(c))[0]
    ziel = os.path.join(LERNEN, "vorreg", f"{name}.json")
    if os.path.exists(ziel):
        alt = json.load(open(ziel, encoding="utf-8"))
        if not any(h.get("status") == "wartet" for h in alt["hypothesen"]):
            continue
    offen.append(c)
if not offen:
    log("alle Chargen bewertet"); sys.exit(0)

sys.path.insert(0, ROOT)
t0 = time.time()
import suchmaschine as sm  # noqa: E402  (versiegelt: alle Reihen am STICHTAG abgeschnitten)
F = sm.FAM["S"]; MR = F["mr"]; P_S = sm.praefix(MR); KOSTEN, N_MIN = sm.KOSTEN, sm.N_MIN
TAB_S = {(e["indikator"], e["art"]): e for e in sm.ereignis_tabelle() if e["fam"] == "S"}
log(f"Suchmaschine geladen: {len(sm.ind)} Indikatoren, {len(TAB_S)} Ereignisreihen S, {(time.time() - t0) / 60:.1f} min")

def gesehen_bis(datum):
    """Schlüssel indikator|art|ziel|h, die vor datum (JJJJ-MM-TT) in einer Bestenliste standen."""
    keys = set()
    for p in glob.glob(os.path.join(LERNEN, "suche", "S*.json")):
        if p.endswith("_analyse.json"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        z = str(d.get("zeit", ""))  # «30.9.2026, 07:12 (Europe/Zurich)»
        try:
            tag = pd.to_datetime(z.split(",")[0], format="%d.%m.%Y").strftime("%Y-%m-%d")
        except Exception:
            tag = "0000-00-00"
        if tag >= datum:
            continue
        for feld in ("staerkste_positive", "staerkste_indizes", "route_c_stufe1", "bausteine", "langzeit_hinweise"):
            for r in d.get(feld) or []:
                if isinstance(r, dict) and "indikator" in r:
                    keys.add(f"{r['indikator']}|{r.get('art')}|{r.get('ziel')}|{int(r.get('h', 0))}")
        stamm = p[:-5]
        u = stamm + "_ueberlebende.csv"
        if os.path.exists(u):
            try:
                for r in pd.read_csv(u).itertuples():
                    keys.add(f"{r.indikator}|{r.art}|{r.ziel}|{int(r.h)}")
            except Exception:
                pass
        a = stamm + "_analyse.json"
        if os.path.exists(a):
            try:
                for r in json.load(open(a, encoding="utf-8")).get("profile", []):
                    keys.add(f"{r['indikator']}|{r['art']}|{r['ziel']}|{int(r['h'])}")
            except Exception:
                pass
    return keys

def bewerte(h, mr, rng, n_f5=sm.N_F5):
    e = TAB_S.get((h["indikator"], h["art"]))
    r = sm.auswerten(F, sm.praefix({(h["ziel"], h["h"]): mr[(h["ziel"], h["h"])]}) if mr is not MR else P_S, mr, e, h["ziel"], h["h"])
    if r is None:
        return None
    a = mr[(h["ziel"], h["h"])]; pos = r["_pos"]
    alt = sm.N_F5; sm.N_F5 = n_f5
    p = sm.f5_rotation(a, pos, r["mu"], rng)
    sm.N_F5 = alt
    v = np.array([q in sm.VERDACHT_POS.get(h["ziel"], set()) for q in pos]); wv = a[pos[~v]]
    tv = float((wv.mean() - r["mu0"]) / (max(r["sd0"], np.std(wv, ddof=1)) / np.sqrt(len(wv)))) if len(wv) > 2 else np.nan
    return dict(n=int(r["n"]), mu=float(r["mu"]), mu0=float(r["mu0"]), t=float(r["t"]), t1=float(r["t1"]), t2=float(r["t2"]),
                p_f5=float(p), n_verdacht=int(v.sum()), t_ohne_verdacht=tv, mu_netto=float(r["mu"] - KOSTEN))

def holm(ps):
    ps = np.asarray(ps, float); m = len(ps); order = np.argsort(ps); adj = np.empty(m); lauf = 0.0
    for rang, i in enumerate(order):
        lauf = max(lauf, min(1.0, (m - rang) * ps[i])); adj[i] = lauf
    return adj

def baustein(x, p_holm):
    return bool(p_holm <= ALPHA and x["mu"] >= KOSTEN and x["n"] >= N_MIN and x["t1"] >= 1 and x["t2"] >= 1
                and (x["t_ohne_verdacht"] >= 2 if not np.isnan(x["t_ohne_verdacht"]) else False))

def rund(v):
    return round(v, 4) if isinstance(v, float) and not np.isnan(v) else (None if isinstance(v, float) else v)

jetzt = pd.Timestamp.utcnow()
for c in offen:
    name = os.path.splitext(os.path.basename(c))[0]
    ch = json.load(open(c, encoding="utf-8"))
    hyps = ch.get("hypothesen", [])[:MAX_JE_CHARGE]
    datum = str(ch.get("charge", name))[:10]
    gesehen = gesehen_bis(datum)
    zeilen = []
    for h in hyps:
        h = dict(h); h["h"] = int(h.get("h", 0)); key = f"{h.get('indikator')}|{h.get('art')}|{h.get('ziel')}|{h['h']}"
        z = {"id": h.get("id"), "schluessel": key, "mechanismus": h.get("mechanismus"), "literatur": h.get("literatur")}
        if h.get("erwartung", "positiv") != "positiv" or h["h"] not in sm.HORIZONTE or h.get("ziel") not in sm.ZIELE \
                or h.get("art") not in ("hoch", "tief", "sprung_auf", "sprung_ab"):
            z["status"] = "ungueltig"
        elif key in gesehen:
            z["status"] = "kontaminiert"
        elif h.get("indikator") not in sm.ind or (h["indikator"], h["art"]) not in TAB_S:
            alter = (jetzt - pd.Timestamp(datum, tz="UTC")).days
            z["status"] = "verfallen" if alter > WARTEFRIST_TAGE else "wartet"
        else:
            z["status"] = "bewertet"; z["_h"] = h
        zeilen.append(z)
    bew = [z for z in zeilen if z["status"] == "bewertet"]
    rng = np.random.default_rng(20261004)
    for z in bew:
        x = bewerte(z["_h"], MR, rng)
        if x is None:
            z["status"] = "ungueltig"; z["grund"] = "keine Referenz oder zu wenige Ereignisse"; continue
        z.update(x)
    bew = [z for z in zeilen if z["status"] == "bewertet"]
    if bew:
        adj = holm([z["p_f5"] for z in bew])
        for z, p in zip(bew, adj):
            z["p_holm"] = float(p); z["v_baustein"] = baustein(z, p)
        # Chargen-Fehlalarm: gemeinsame Rotation aller Zielrenditen, gleiche Auswertung
        treffer = 0
        prng = np.random.default_rng(777)
        for s in range(N_ROT_CHARGE):
            o = int(prng.integers(252 // 5, (F["ende"] - 252) // 5)) * 5
            mr = {k: np.roll(a, o) for k, a in MR.items()}
            xs = [bewerte(z["_h"], mr, prng, n_f5=2000) for z in bew]
            ok = [(x, i) for i, x in enumerate(xs) if x is not None]
            if not ok:
                continue
            adj_r = holm([x["p_f5"] for x, _ in ok])
            treffer += int(any(baustein(x, p) for (x, _), p in zip(ok, adj_r)))
        fehl = treffer / N_ROT_CHARGE
    else:
        fehl = None
    for z in zeilen:
        z.pop("_h", None)
        for k in list(z):
            z[k] = rund(z[k])
    n_b = sum(1 for z in zeilen if z.get("v_baustein"))
    erg = {"charge": name, "verfassung": "V3.10", "familie": "V", "bewertet_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ"),
           "registriert_utc": ch.get("registriert_utc"), "autor": ch.get("autor"), "kosten_pp_je_wechsel": KOSTEN,
           "anzahl": {s: sum(1 for z in zeilen if z["status"] == s) for s in ("bewertet", "kontaminiert", "wartet", "verfallen", "ungueltig")},
           "v_bausteine": n_b, "fehlalarm_charge": rund(fehl) if fehl is not None else None, "rotationen": N_ROT_CHARGE,
           "fund": bool(n_b >= 1),
           "urteil": ("FUND (Familie V) – Fixierung durch Reto nötig. Siegel nicht geöffnet." if n_b else
                      "Kein V-Baustein. Validierung ab 2021 nicht angerührt (S4)."),
           "hypothesen": zeilen}
    json.dump(erg, open(os.path.join(LERNEN, "vorreg", f"{name}.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = os.path.join(LERNEN, "index.json")
    if os.path.exists(ip):
        idx = json.load(open(ip, encoding="utf-8"))
        idx.setdefault("vorreg", [])
        idx["vorreg"] = [v for v in idx["vorreg"] if v.get("charge") != name] + [
            {"charge": name, "datei": f"vorreg/{name}.json", "v_bausteine": n_b, "fund": bool(n_b >= 1), "in_db": False}]
        json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"Charge {name}: {erg['anzahl']}, V-Bausteine {n_b}, Fehlalarm {erg['fehlalarm_charge']}")
log(f"fertig in {(time.time() - t0) / 60:.1f} min")
