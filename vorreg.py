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

Methodenstand V3.10.1 (2.10.2026, Reto: «Paket 1 wie vorgeschlagen»; Fehlerkorrekturen nach Astra-Gegenprüfung 3):
  Zeitstempel  «gesehen» wird mit vollen UTC-Zeitstempeln entschieden: ein Suchlauf gilt als gesehen, wenn seine Zeit
               nicht nach registriert_utc liegt oder nicht lesbar ist. Fehlt registriert_utc, gelten alle Läufe bis
               zum Ende des Chargentags als gesehen.
  Einmaligkeit Das Ergebnis einer Hypothese (n, mu, t, p_f5, …) wird beim ersten Bewerten gespeichert und nie neu
               gerechnet (bewertet_utc, code_hash, daten_hash, methodenstand je Zeile). Auch «kontaminiert»,
               «ungueltig» und «verfallen» sind endgültig. Nur «wartet» wird erneut geprüft.
  Holm         über die REGISTRIERTE Familie der Charge (alle Hypothesen der Datei, höchstens 10); nicht bewertete
               zählen mit p = 1. Ein früh vergebener V-Baustein bleibt dadurch gültig; das Urteil der Charge ist
               erst endgültig, wenn keine Hypothese mehr wartet (charge_vollstaendig).
  Zufall       eigener, aus dem Schlüssel abgeleiteter Startwert je Hypothese (unabhängig von der Reihenfolge).
"""
import glob, gzip, hashlib, io, json, os, re, sys, time
import numpy as np, pandas as pd

def log(*a):
    print(*a, file=sys.stderr, flush=True)

ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.path.join(ROOT, "_lernen")
MAX_JE_CHARGE, WARTEFRIST_TAGE, N_ROT_CHARGE, ALPHA = 10, 60, 200, 0.05
METHODENSTAND = "V3.10.1"
ENDGUELTIG = ("bewertet", "kontaminiert", "ungueltig", "verfallen")
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

def sha_datei(pfad):
    try:
        return hashlib.sha256(open(pfad, "rb").read()).hexdigest()
    except OSError:
        return ""

CODE_HASH = hashlib.sha256("".join(sha_datei(os.path.join(ROOT, f)) for f in
                                   ("suchmaschine.py", "vorreg.py", "paare.txt", "mechanismen.txt", "korrekturen_neu.json")).encode()).hexdigest()[:16]

def zeit_utc(z):
    """«30.9.2026, 07:12 (Europe/Zurich)» oder ISO-Zeit -> UTC-Zeitstempel; None, wenn nicht lesbar."""
    z = str(z or "").strip()
    try:
        m = re.match(r"^(\d{1,2})\.(\d{1,2})\.(\d{4}),\s*(\d{1,2}):(\d{2})(?::(\d{2}))?\s*(?:\(([^)]+)\))?$", z)
        if m:
            t, mo, j, st, mi, se, zone = m.groups()
            ts = pd.Timestamp(year=int(j), month=int(mo), day=int(t), hour=int(st), minute=int(mi), second=int(se or 0))
            return ts.tz_localize(zone or "Europe/Zurich", ambiguous=False, nonexistent="shift_forward").tz_convert("UTC")
        if not re.match(r"^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}", z):
            return None
        ts = pd.Timestamp(z)
        return ts.tz_localize("UTC") if ts.tzinfo is None else ts.tz_convert("UTC")
    except Exception:
        return None

def grenze_utc(ch, datum):
    """Zeitpunkt der Registrierung. Ohne lesbares registriert_utc: Ende des Chargentags (vorsichtig)."""
    g = zeit_utc(ch.get("registriert_utc"))
    if g is not None:
        return g, "registriert_utc"
    return pd.Timestamp(datum, tz="UTC") + pd.Timedelta(hours=23, minutes=59, seconds=59), "Ende des Chargentags (registriert_utc fehlt oder unlesbar)"

def gesehen_bis(grenze):
    """Schlüssel indikator|art|ziel|h, die bis zum Zeitpunkt grenze (UTC) in einer Bestenliste standen.
    Ein Lauf mit unlesbarer Zeit gilt als gesehen (vorsichtig)."""
    keys = set()
    for p in glob.glob(os.path.join(LERNEN, "suche", "S*.json")):
        if p.endswith("_analyse.json"):
            continue
        try:
            d = json.load(open(p, encoding="utf-8"))
        except Exception:
            continue
        zt = zeit_utc(d.get("zeit"))
        if zt is not None and zt > grenze:
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
    tv = x.get("t_ohne_verdacht")
    return bool(p_holm <= ALPHA and x["mu"] >= KOSTEN and x["n"] >= N_MIN and x["t1"] >= 1 and x["t2"] >= 1
                and tv is not None and not np.isnan(tv) and tv >= 2)

def rund(v):
    return round(v, 4) if isinstance(v, float) and not np.isnan(v) else (None if isinstance(v, float) else v)

def startwert(key):
    return int(hashlib.sha256(("F5|" + key).encode()).hexdigest()[:12], 16)

def daten_hash(h):
    """Fingerabdruck der Daten hinter einer Bewertung: Ereignispositionen und Mehrrenditen des Ziels."""
    e = TAB_S[(h["indikator"], h["art"])]; a = MR[(h["ziel"], h["h"])]
    return hashlib.sha256(np.asarray(e["pos"], dtype=np.int64).tobytes() + np.nan_to_num(np.asarray(a, dtype=np.float64), nan=-9e9).tobytes()).hexdigest()[:16]

def charge_pruefen(name, ch, alt, jetzt):
    """Gibt (zeilen, neu, grenze, grenze_art) zurück. zeilen: eine je registrierte Hypothese; gespeicherte endgültige Zeilen unverändert."""
    hyps = ch.get("hypothesen", [])[:MAX_JE_CHARGE]
    datum = str(ch.get("charge", name))[:10]
    grenze, grenze_art = grenze_utc(ch, datum)
    gesehen = gesehen_bis(grenze)
    alt_z = {z.get("schluessel"): z for z in (alt or {}).get("hypothesen", [])}
    zeilen, neu = [], 0
    for h in hyps:
        h = dict(h)
        try:
            h["h"] = int(h.get("h", 0))
        except (TypeError, ValueError):
            h["h"] = 0
        key = f"{h.get('indikator')}|{h.get('art')}|{h.get('ziel')}|{h['h']}"
        a = alt_z.get(key)
        if a is not None and a.get("status") in ENDGUELTIG:
            a = dict(a); a["_h"] = h
            if a["status"] == "bewertet":
                a.setdefault("bewertet_utc", alt.get("bewertet_utc"))
                a.setdefault("methodenstand", alt.get("verfassung", "V3.10"))
            zeilen.append(a); continue
        z = {"id": h.get("id"), "schluessel": key, "mechanismus": h.get("mechanismus"), "literatur": h.get("literatur"), "_h": h}
        if h.get("erwartung", "positiv") != "positiv" or h["h"] not in sm.HORIZONTE or h.get("ziel") not in sm.ZIELE \
                or h.get("art") not in ("hoch", "tief", "sprung_auf", "sprung_ab"):
            z["status"] = "ungueltig"
        elif key in gesehen:
            z["status"] = "kontaminiert"
        elif h.get("indikator") not in sm.ind or (h["indikator"], h["art"]) not in TAB_S:
            alter = (jetzt - pd.Timestamp(datum, tz="UTC")).days
            z["status"] = "verfallen" if alter > WARTEFRIST_TAGE else "wartet"
        else:
            x = bewerte(h, MR, np.random.default_rng(startwert(key)))
            if x is None:
                z["status"] = "ungueltig"; z["grund"] = "keine Referenz oder zu wenige Ereignisse"
            else:
                z["status"] = "bewertet"; z.update(x)
                z.update({"bewertet_utc": jetzt.strftime("%Y-%m-%dT%H:%M:%SZ"), "code_hash": CODE_HASH,
                          "daten_hash": daten_hash(h), "methodenstand": METHODENSTAND})
        if z["status"] != "wartet" or a is None:
            neu += 1
        zeilen.append(z)
    return zeilen, neu, grenze, grenze_art

def holm_familie(zeilen):
    """Holm über die registrierte Familie; nicht bewertete Hypothesen zählen mit p = 1."""
    ps = [float(z["p_f5"]) if z["status"] == "bewertet" else 1.0 for z in zeilen]
    return holm(ps) if ps else np.array([])

jetzt = pd.Timestamp.now(tz="UTC")
for c in offen:
    name = os.path.splitext(os.path.basename(c))[0]
    ch = json.load(open(c, encoding="utf-8"))
    zp = os.path.join(LERNEN, "vorreg", f"{name}.json")
    alt = json.load(open(zp, encoding="utf-8")) if os.path.exists(zp) else None
    zeilen, neu, grenze, grenze_art = charge_pruefen(name, ch, alt, jetzt)
    if alt is not None and neu == 0:
        log(f"Charge {name}: nichts Neues (weiter wartend), Ergebnisdatei unverändert"); continue
    adj = holm_familie(zeilen)
    for z, p in zip(zeilen, adj):
        if z["status"] == "bewertet":
            z["p_holm"] = float(p)
            z["v_baustein"] = bool(z.get("v_baustein")) or baustein(z, p)   # ein vergebener Baustein bleibt (Holm ist hier vorsichtig)
    bew = [(i, z) for i, z in enumerate(zeilen) if z["status"] == "bewertet"]
    if bew:
        # Chargen-Fehlalarm (Diagnose): gemeinsame Rotation aller Zielrenditen, gleiche Auswertung, gleiche Familiengrösse
        treffer = 0
        prng = np.random.default_rng(777)
        for s in range(N_ROT_CHARGE):
            o = int(prng.integers(252 // 5, (F["ende"] - 252) // 5)) * 5
            mr = {k: np.roll(a, o) for k, a in MR.items()}
            ps = [1.0] * len(zeilen); xs = {}
            for i, z in bew:
                x = bewerte(z["_h"], mr, prng, n_f5=2000)
                if x is not None:
                    xs[i] = x; ps[i] = x["p_f5"]
            adj_r = holm(ps)
            treffer += int(any(baustein(x, adj_r[i]) for i, x in xs.items()))
        fehl = treffer / N_ROT_CHARGE
    else:
        fehl = None
    for z in zeilen:
        z.pop("_h", None)
        for k in list(z):
            z[k] = rund(z[k])
    n_b = sum(1 for z in zeilen if z.get("v_baustein"))
    vollst = not any(z["status"] == "wartet" for z in zeilen)
    erg = {"charge": name, "verfassung": "V3.10", "methodenstand": METHODENSTAND, "familie": "V",
           "bewertet_utc": jetzt.strftime("%Y-%m-%dT%H:%MZ"), "erstbewertung_utc": (alt or {}).get("erstbewertung_utc") or (alt or {}).get("bewertet_utc") or jetzt.strftime("%Y-%m-%dT%H:%MZ"),
           "registriert_utc": ch.get("registriert_utc"), "gesehen_grenze_utc": grenze.strftime("%Y-%m-%dT%H:%M:%SZ"), "gesehen_grenze_art": grenze_art,
           "autor": ch.get("autor"), "kosten_pp_je_wechsel": KOSTEN, "code_hash": CODE_HASH,
           "familie_n": len(zeilen), "holm": "über alle registrierten Hypothesen der Charge; nicht bewertete mit p = 1",
           "charge_vollstaendig": vollst,
           "anzahl": {s: sum(1 for z in zeilen if z["status"] == s) for s in ("bewertet", "kontaminiert", "wartet", "verfallen", "ungueltig")},
           "v_bausteine": n_b, "fehlalarm_charge": rund(fehl) if fehl is not None else None, "rotationen": N_ROT_CHARGE,
           "fehlalarm_art": "Diagnose (Rotationsmodell nicht validiert), kein Teil der Entscheidregel",
           "fund": bool(n_b >= 1),
           "urteil": ("FUND (Familie V) – Fixierung durch Reto nötig. Siegel nicht geöffnet." if n_b else
                      ("Kein V-Baustein. Validierung ab 2021 nicht angerührt (S4)." if vollst else
                       "Bisher kein V-Baustein; Charge noch nicht vollständig bewertet. Validierung ab 2021 nicht angerührt (S4).")),
           "hypothesen": zeilen}
    json.dump(erg, open(zp, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    ip = os.path.join(LERNEN, "index.json")
    if os.path.exists(ip):
        idx = json.load(open(ip, encoding="utf-8"))
        idx.setdefault("vorreg", [])
        idx["vorreg"] = [v for v in idx["vorreg"] if v.get("charge") != name] + [
            {"charge": name, "datei": f"vorreg/{name}.json", "v_bausteine": n_b, "fund": bool(n_b >= 1), "vollstaendig": vollst, "in_db": False}]
        json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    log(f"Charge {name}: {erg['anzahl']}, V-Bausteine {n_b}, Fehlalarm {erg['fehlalarm_charge']}, vollständig {vollst}")
log(f"fertig in {(time.time() - t0) / 60:.1f} min")
