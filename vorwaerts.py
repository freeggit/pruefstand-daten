"""Prüfstand – Vorwärtsregister (Verfassung V3.14, E32/E33): Logbuch der Auslöser registrierter Stränge.

Ein Strang ist eine feste Regel oder ein Bündel aus 2 bis 5 Regeln (gleich gewichtet, ein Endpunkt). Er wird als Datei
vorwaerts/<Kennung>.json auf main registriert (der Commit ist der Zeitstempel) und danach nie mehr geändert.

Täglicher Lauf (Standard): Für jeden Strang werden die Auslöser NACH dem Registriertag bestimmt und im Logbuch
festgehalten: Beobachtungstag, Wert des Indikators, Zeitpunkt der Erkennung, Einstiegstag nach der Fristregel der Suche.
Das Logbuch wird nur verlängert. Der Lauf liest KEINE Zielkurse nach dem Stichtag und rechnet keine Erträge; es gibt
keine Zwischenstände (E32: keine Zwischenentscheide).

Siegel: Der Lauf baut die Indikatoren mit dem unveränderten Code der Suche (suchmaschine.py), aber mit zwei genau
festgelegten Ersetzungen in einer privaten Kopie im Speicher: Signalreihen reichen bis heute, Kurse bleiben am Stichtag
abgeschnitten. Die Datei suchmaschine.py wird nicht verändert; die Suche bleibt unberührt. Signalwerte vor dem
Registriertag werden nur für die rollenden Schwellen gebraucht und nie ausgegeben (V3.14, P1). Der Handelskalender
nach dem Stichtag stammt allein aus der Datumsspalte der ACWI-Datei (keine Kurse).

Schlussauswertung (PS_VORWAERTS_SCHLUSS=<Kennung>): frühestens am Schlusstag, einmal, mit dem Test der Bestätigung
(bestaetigung.py). Erst dann werden Zielkurse des Strangs gelesen. Gewertet werden nur Auslöser, die vor der Eröffnung
des Einstiegstags erkannt waren; alle anderen gelten als verpasst und werden gezählt.

Aufruf: python vorwaerts.py   (in der Action; Daten neben dem Skript)   oder   python vorwaerts.py <BASIS>
Umgebung: PS_VORWAERTS_DIR (Registrierungen, Standard: vorwaerts neben dem Skript), PS_VORWAERTS_LOG (Ordner des Logbuchs),
PS_VORWAERTS_HEUTE (JJJJ-MM-TT, nur für Tests), PS_VORWAERTS_STAND (Text zum Datenstand, z. B. Commits).
Tests: python test_vorwaerts.py
"""
import datetime, hashlib, json, math, os, sys, types
import numpy as np

HIER = os.path.dirname(os.path.abspath(__file__))
MAX_STRAENGE = 3             # gleichzeitig, Typ K eingerechnet (E33, V3.14 P3)
MAX_JAHRE = 5.0              # längere Stränge werden nicht registriert (V3.14 P2, E36)
MIN_EREIGNISSE = 10
NIVEAU, STAERKE, ALTERNATIVE = 0.05, 0.40, 3.0
HALTEDAUERN = (1, 5, 20)
HALTEDAUERN_K = (60, 120, 250)
EROEFFNUNG_UTC = datetime.time(13, 30)   # früheste Eröffnung der US-Börse in UTC (Sommerzeit); im Winter 14:30, also vorsichtig
PFLICHT = ("kennung", "art", "registriert", "regeln", "kosten_pp", "niveau", "test", "letzter_einstieg", "schlusstag",
           "min_ereignisse", "vorpruefung", "freigabe", "mechanismus")
UNTERTAEGIG = ("wetter_", "strom_")   # Indikatoren aus Stundenwerten (Tagesmittel); der letzte Tag kann unvollständig sein
N_BIS_ERWARTET = 11          # Vorkommen von «bis(» in suchmaschine.py samt Definition; ändert sich das, bricht der Lauf ab


# ============================================================================================== reine Funktionen
def dauer_jahre(jahresschwankung, alternative=ALTERNATIVE, niveau=NIVEAU, staerke=STAERKE):
    """Nötige Dauer in Jahren (Normalnäherung), aufgerundet auf volle Halbjahre."""
    from statistics import NormalDist
    z = NormalDist().inv_cdf(1 - niveau) + NormalDist().inv_cdf(staerke)
    return math.ceil(2 * (jahresschwankung * z / alternative) ** 2 - 1e-9) / 2.0


def sha(text):
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _tag(s):
    return datetime.date.fromisoformat(s)


def pruefe_registrierung(d):
    """Gibt eine Liste von Fehlern zurück (leer = gültig). Prüft nur die Form; Reihen und Ziele prüft der Lauf."""
    f = [f"Feld fehlt: {k}" for k in PFLICHT if k not in d]
    if f:
        return f
    if d["art"] not in ("strang", "uebung", "typ_k"):
        f.append("art muss strang, uebung oder typ_k sein")
    r = d["regeln"]
    if not isinstance(r, list) or not 1 <= len(r) <= 5:
        f.append("1 bis 5 Regeln"); return f
    erlaubt = HALTEDAUERN_K if d["art"] == "typ_k" else HALTEDAUERN
    for x in r:
        if set(x) != {"indikator", "art", "ziel", "h"}:
            f.append(f"Regel braucht genau indikator, art, ziel, h: {x}"); continue
        if x["art"] not in ("hoch", "tief", "sprung_auf", "sprung_ab"):
            f.append(f"Extremtyp unbekannt: {x['art']}")
        if x["h"] not in erlaubt:
            f.append(f"Haltedauer {x['h']} nicht zulässig für art {d['art']}")
    if len({x.get("ziel") for x in r}) != len(r):
        f.append("je Ziel höchstens eine Regel")
    try:
        reg, le, st = _tag(d["registriert"]), _tag(d["letzter_einstieg"]), _tag(d["schlusstag"])
        hmax = max(int(x.get("h", 0)) for x in r)
        if not reg < le < st:
            f.append("Reihenfolge: registriert < letzter_einstieg < schlusstag")
        if (st - le).days < math.ceil(hmax * 7 / 5) + 7:
            f.append("alle Haltefenster müssen vor dem Schlusstag auslaufen (Haltedauer plus 7 Kalendertage Reserve)")
        if d["art"] != "uebung" and (st - reg).days / 365.25 > MAX_JAHRE + 0.1:
            f.append(f"Dauer über {MAX_JAHRE} Jahre")
    except (ValueError, TypeError):
        f.append("Datum nicht lesbar (JJJJ-MM-TT)")
    t = d["test"]
    if not isinstance(t, dict) or t.get("name") != "blocktest" or t.get("block") != 20 or t.get("ziehungen") != 10000 or not isinstance(t.get("startwert"), int):
        f.append("test: {name blocktest, block 20, ziehungen 10000, startwert ganzzahlig}")
    if d["niveau"] != NIVEAU:
        f.append("niveau muss 0.05 sein")
    if d["min_ereignisse"] < MIN_EREIGNISSE:
        f.append(f"min_ereignisse mindestens {MIN_EREIGNISSE}")
    if not (isinstance(d["kosten_pp"], (int, float)) and d["kosten_pp"] > 0):
        f.append("kosten_pp positiv")
    return f


def erkannt_rechtzeitig(erkannt_utc, einstieg):
    """Papierhandel: gewertet wird nur, was vor der Eröffnung des Einstiegstags erkannt war."""
    e = datetime.datetime.strptime(erkannt_utc, "%Y-%m-%dT%H:%M:%SZ")
    return e < datetime.datetime.combine(_tag(einstieg), EROEFFNUNG_UTC)


def fortschreiben(alt, gefunden, reihe_bis_vorher, jetzt_utc):
    """Vergleicht den bisherigen Stand eines Schlüssels (strang, regel) mit den jetzt gefundenen Auslösern.
    alt: Liste früherer Logzeilen dieses Schlüssels; gefunden: {beobachtung: (wert, einstieg oder None)}.
    Gibt neue Logzeilen zurück. Nichts wird geändert oder gelöscht; Abweichungen werden als neue Zeilen gekennzeichnet."""
    stand = {}                                                 # letzter bekannter Zustand je Beobachtungstag
    for z in alt:
        stand[z["beobachtung"]] = z
    neu = []
    for b in sorted(gefunden):
        wert, ein = gefunden[b]
        z = stand.get(b)
        if z is None or z["ereignis"] == "entfallen":
            spaet = reihe_bis_vorher is not None and b <= reihe_bis_vorher
            neu.append(dict(ereignis="ausloeser", beobachtung=b, wert=wert, einstieg=ein, erkannt_utc=jetzt_utc,
                            kennzeichen="nachlieferung" if spaet else None))
        elif z.get("einstieg") is None and ein is not None:
            neu.append(dict(ereignis="einstieg_bestimmt", beobachtung=b, wert=wert, einstieg=ein, erkannt_utc=jetzt_utc,
                            kennzeichen=None))
    for b, z in sorted(stand.items()):
        if z["ereignis"] != "entfallen" and b not in gefunden:
            neu.append(dict(ereignis="entfallen", beobachtung=b, wert=None, einstieg=None, erkannt_utc=jetzt_utc,
                            kennzeichen="quelle nachträglich geändert"))
    return neu


def wertbare(zeilen):
    """Aus den Logzeilen eines Schlüssels die gewerteten Einstiegstage und die Zahl der verpassten Auslöser.
    Massgebend ist die ERSTE Zeile «ausloeser» je Beobachtungstag (Zeitpunkt der Erkennung); der Einstiegstag darf später
    bestimmt worden sein. Entfallene Auslöser bleiben gewertet, wenn sie rechtzeitig erkannt waren (auf Papier gehandelt)."""
    erst, ein = {}, {}
    for z in zeilen:
        b = z["beobachtung"]
        if z["ereignis"] == "ausloeser" and b not in erst:
            erst[b] = z
        if z["ereignis"] in ("ausloeser", "einstieg_bestimmt") and z.get("einstieg") and b not in ein:
            ein[b] = z["einstieg"]
    gut, verpasst = [], 0
    for b, z in sorted(erst.items()):
        e = ein.get(b)
        if e is None:
            continue                                           # Einstiegstag liegt noch in der Zukunft
        if z.get("kennzeichen") != "nachlieferung" and erkannt_rechtzeitig(z["erkannt_utc"], e):
            gut.append(e)
        else:
            verpasst += 1
    return sorted(set(gut)), verpasst


# ============================================================================================== Motor (private Kopie)
def motor_laden(signal_bis):
    """Baut die Indikatoren mit dem Code der Suche; Signalreihen bis signal_bis, Kurse weiter am Stichtag abgeschnitten."""
    pfad = os.path.join(HIER, "suchmaschine.py")
    src = open(pfad, encoding="utf-8").read()
    a = "def bis(x, tag=STICHTAG):"
    b = 'd = bis(pd.read_csv(lade(f"kurse/{t}_d.csv")'
    if src.count(a) != 1 or src.count(b) != 1 or src.count("bis(") != N_BIS_ERWARTET:
        raise SystemExit("ABBRUCH: suchmaschine.py hat sich an den Stellen des Stichtags geändert; vorwaerts.py zuerst prüfen.")
    src = src.replace(a, f'SIGNAL_BIS = pd.Timestamp("{signal_bis}")\n'
                         "def bis_kurs(x):\n    return x[x.index <= STICHTAG]\n\n"
                         "def bis(x, tag=SIGNAL_BIS):")
    src = src.replace(b, 'd = bis_kurs(pd.read_csv(lade(f"kurse/{t}_d.csv")')
    m = types.ModuleType("motor_vorwaerts"); m.__file__ = pfad
    exec(compile(src, pfad, "exec"), m.__dict__)
    spaet = [t for t, d in list(m.kurse.items()) + [("acwi", m.acwi)] if len(d) and d.index.max() > m.STICHTAG]
    if spaet:
        raise SystemExit(f"ABBRUCH: Kurse nach dem Stichtag geladen ({spaet[:3]}); Siegel verletzt.")
    return m


def kalender(m, heute):
    """Handelskalender: Discovery-Kalender der Suche plus die Datumsspalte der ACWI-Datei bis heute (keine Kurse)."""
    import pandas as pd
    d = pd.read_csv(m.lade("kurse/acwi_d.csv"), usecols=["Date"], parse_dates=["Date"]).Date.drop_duplicates().sort_values()
    d = d[(d > m.STICHTAG) & (d <= pd.Timestamp(heute))]
    k = m.KAL.append(pd.DatetimeIndex(d))
    return k[k <= pd.Timestamp(heute)]


def ausloeser(m, kal, regel, nach):
    """Auslöser einer Regel mit Beobachtungstag nach «nach» (Registriertag). Gibt ({beobachtung: (wert, einstieg)}, reihe_bis)."""
    import pandas as pd
    ind = regel["indikator"]
    if ind not in m.ind:
        return None, None
    x, fristen = m.ind[ind]
    tage = m.ereignisse(x, regel["art"], ind in m.EREIGNIS)
    tage = tage[(tage > pd.Timestamp(nach)) & (tage < m.SIGNAL_BIS)]     # der laufende Tag ist nie abgeschlossen und zählt nicht
    xs = x.dropna()
    reihe_bis = str(xs.index[-1].date()) if len(xs) else None
    if ind.startswith(UNTERTAEGIG) and len(xs):
        tage = tage[tage < xs.index[-1]]             # Reihen aus Stundenwerten: der letzte Tag kann unvollständig sein und zählt nie
    out = {}
    if len(tage):
        pos = m.einstieg(kal, tage, fristen)
        for t, p in zip(tage, pos):
            ein = str(kal[p].date()) if 0 <= p < len(kal) else None
            out[str(t.date())] = (float(x.loc[t]), ein)
    return out, reihe_bis


# ============================================================================================== täglicher Lauf
def registrierungen(ordner):
    out = []
    if os.path.isdir(ordner):
        for n in sorted(os.listdir(ordner)):
            if n.endswith(".json"):
                text = open(os.path.join(ordner, n), encoding="utf-8").read()
                out.append((n, text, json.loads(text)))
    return out


def lesen_jsonl(p):
    return [json.loads(z) for z in open(p, encoding="utf-8") if z.strip()] if os.path.exists(p) else []


def lauf(ordner, logdir, heute, jetzt_utc, datenstand=""):
    if not registrierungen(ordner) and not os.path.exists(os.path.join(logdir, "stand.json")):
        return dict(zeit_utc=jetzt_utc, heute=str(heute), datenstand=datenstand, registrierungen=0, aktiv=[], straenge_je_registriert=0,
                    neue_zeilen=0, regeln=[], fehler=[])       # leeres Register: nichts schreiben
    os.makedirs(logdir, exist_ok=True)
    p_log, p_stand, p_laeufe = (os.path.join(logdir, n) for n in ("logbuch.jsonl", "stand.json", "laeufe.jsonl"))
    stand = json.load(open(p_stand, encoding="utf-8")) if os.path.exists(p_stand) else {"registrierungen": {}, "reihe_bis": {}}
    log = lesen_jsonl(p_log)
    regs, fehler, aktiv = registrierungen(ordner), [], []
    for name, text, d in regs:
        k = d.get("kennung", name)
        f = pruefe_registrierung(d)
        if name != f"{k}.json":
            f.append("Dateiname muss <kennung>.json sein")
        h = sha(text); alt = stand["registrierungen"].get(k)
        if alt is None:
            if not f and _tag(d["registriert"]) > heute:
                f.append("Registriertag liegt in der Zukunft")
            if not f:
                stand["registrierungen"][k] = dict(sha256=h, erstmals_gesehen_utc=jetzt_utc, registriert=d["registriert"])
        elif alt["sha256"] != h:
            f.append("REGISTRIERUNG NACHTRÄGLICH VERÄNDERT: Strang gestoppt")
        if f:
            fehler.append(dict(kennung=k, fehler=f)); continue
        if heute <= _tag(d["schlusstag"]):
            aktiv.append(d)
    echte = [d for d in aktiv if d["art"] != "uebung"]
    if len(echte) > MAX_STRAENGE:
        zuviel = sorted(echte, key=lambda d: (stand["registrierungen"][d["kennung"]]["erstmals_gesehen_utc"], d["kennung"]))[MAX_STRAENGE:]
        for d in zuviel:
            fehler.append(dict(kennung=d["kennung"], fehler=[f"mehr als {MAX_STRAENGE} Stränge gleichzeitig; dieser läuft nicht mit"]))
        aktiv = [d for d in aktiv if d not in zuviel]
    neu, bericht = [], []
    if aktiv:
        m = motor_laden(str(heute)); kal = kalender(m, heute)
        for d in aktiv:
            k = d["kennung"]; reihen = {m.quelle_von(r["indikator"]) for r in d["regeln"]}
            if len(reihen) != len(d["regeln"]) or any(r["ziel"] not in m.ZIELE for r in d["regeln"]):
                fehler.append(dict(kennung=k, fehler=["je Grundreihe höchstens eine Regel; Ziel muss zur Familie S gehören"])); continue
            for i, r in enumerate(d["regeln"]):
                key = f"{k}|{i}"
                gef, reihe_bis = ausloeser(m, kal, r, d["registriert"])
                if gef is None:
                    neu.append(dict(strang=k, regel=i, ereignis="ausfall", beobachtung=None, wert=None, einstieg=None,
                                    erkannt_utc=jetzt_utc, kennzeichen="Indikator heute nicht im Suchraum"))
                    bericht.append(dict(strang=k, regel=i, reihe_bis=None, neu=0)); continue
                gef = {b: v for b, v in gef.items() if v[1] is None or _tag(v[1]) <= _tag(d["letzter_einstieg"])}
                alt = [z for z in log if z["strang"] == k and z["regel"] == i and z["ereignis"] != "ausfall"]
                zeilen = fortschreiben(alt, gef, stand["reihe_bis"].get(key), jetzt_utc)
                neu += [dict(strang=k, regel=i, **z) for z in zeilen]
                stand["reihe_bis"][key] = reihe_bis
                bericht.append(dict(strang=k, regel=i, reihe_bis=reihe_bis, neu=len(zeilen)))
    with open(p_log, "a", encoding="utf-8") as f:
        for z in neu:
            f.write(json.dumps(z, ensure_ascii=False, allow_nan=False) + "\n")
    json.dump(stand, open(p_stand, "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    zus = dict(zeit_utc=jetzt_utc, heute=str(heute), datenstand=datenstand, registrierungen=len(regs), aktiv=[d["kennung"] for d in aktiv],
               straenge_je_registriert=len(stand["registrierungen"]), neue_zeilen=len(neu), regeln=bericht, fehler=fehler)
    with open(p_laeufe, "a", encoding="utf-8") as f:
        f.write(json.dumps(zus, ensure_ascii=False) + "\n")
    return zus


# ============================================================================================== Schlussauswertung
def schluss(ordner, logdir, kennung, heute, jetzt_utc):
    import pandas as pd
    import bestaetigung as bt
    name, text, d = next(x for x in registrierungen(ordner) if x[2].get("kennung") == kennung)
    stand = json.load(open(os.path.join(logdir, "stand.json"), encoding="utf-8"))
    p_aus = os.path.join(logdir, f"schluss_{kennung}.json")
    if d["art"] == "uebung":
        raise SystemExit("ABBRUCH: Übungsstränge werden nicht ausgewertet.")
    if heute < _tag(d["schlusstag"]):
        raise SystemExit("ABBRUCH: vor dem Schlusstag gibt es keine Auswertung (E32: keine Zwischenentscheide).")
    if os.path.exists(p_aus):
        raise SystemExit("ABBRUCH: Dieser Strang ist bereits ausgewertet; es gibt genau eine Schlussauswertung.")
    if stand["registrierungen"].get(kennung, {}).get("sha256") != sha(text):
        raise SystemExit("ABBRUCH: Registrierung stimmt nicht mit dem Stand des Logbuchs überein.")
    import suchmaschine as sm                        # nur für lade() und die Kursaufbereitung; Daten der Suche bleiben abgeschnitten
    log = lesen_jsonl(os.path.join(logdir, "logbuch.jsonl"))

    def kurs(t):                                     # Kurse des Strangs nach dem Registriertag, aufbereitet wie in der Suche
        k = pd.read_csv(sm.lade(f"kurse/{t}_d.csv"), parse_dates=["Date"]).drop_duplicates("Date").set_index("Date").sort_index()
        if "AdjClose" in k and k.AdjClose.notna().mean() > 0.99:
            f = (k.AdjClose / k.Close).astype(float); k = pd.DataFrame({"Open": k.Open * f, "Close": k.AdjClose}).astype(float)
        else:
            k = k[["Open", "Close"]].astype(float)
        return k[(k.index > pd.Timestamp(d["registriert"])) & (k.index <= pd.Timestamp(d["schlusstag"]))]
    a = kurs("acwi"); kal = a.index

    def tag(k):
        k = k.reindex(kal); o = k.Open.values; c = k.Close.values
        return c / o - 1, np.r_[np.nan, c[1:] / c[:-1] - 1]
    ao, ac = tag(a); X, n_ev, verpasst = [], 0, 0
    for i, r in enumerate(d["regeln"]):
        zeilen = [z for z in log if z["strang"] == kennung and z["regel"] == i and z["ereignis"] != "ausfall"]
        gut, vp = wertbare(zeilen); verpasst += vp
        pos = kal.get_indexer(pd.DatetimeIndex(gut)); pos = pos[pos >= 0]
        oz, cz = tag(kurs(r["ziel"]))
        x, g = bt.tagesertrag(oz, cz, ao, ac, pos, int(r["h"]), float(d["kosten_pp"]))
        X.append(x); n_ev += len(g)
    x = np.mean(X, axis=0)
    rng = np.random.default_rng(int(d["test"]["startwert"]))
    k_, b_, mittel = bt.blocktest(x, rng, block=20, ziehungen=10000)
    p = bt.p_wert(k_, b_) if k_ is not None else None
    if n_ev < int(d["min_ereignisse"]) or p is None:
        urteil = "unentschieden"
    else:
        urteil = "bewährt" if p <= float(d["niveau"]) else "nicht bewährt"
    erg = dict(kennung=kennung, ausgewertet_utc=jetzt_utc, registriert=d["registriert"], schlusstag=d["schlusstag"], handelstage=int(len(x)),
               ereignisse_gewertet=int(n_ev), ereignisse_verpasst=int(verpasst), mittel_pp_je_tag=float(mittel),
               jahresertrag_netto_pp=float(x.sum() / (len(x) / 252.0)), zaehler=k_, nenner=b_, p=p, niveau=d["niveau"], urteil=urteil,
               straenge_je_registriert=len(stand["registrierungen"]), sha256_registrierung=sha(text),
               hinweis="Das Urteil ist kein Auftrag zu handeln. Über Folgen entscheidet Reto.")
    json.dump(erg, open(p_aus, "w", encoding="utf-8"), ensure_ascii=False, indent=1, allow_nan=False)
    return erg


if __name__ == "__main__":
    if len(sys.argv) < 2:                                      # in der Action: Daten neben dem Skript (wie vorreg.py)
        sys.argv = [sys.argv[0], "file://" + os.path.join(HIER, "data")]
        for pfad, var in (("_daten-energie", "PS_BASIS_ENERGIE"), ("_daten-neu", "PS_BASIS_NEU")):
            if var not in os.environ and os.path.isdir(os.path.join(HIER, pfad, "data")):
                os.environ[var] = "file://" + os.path.join(HIER, pfad, "data")
    ordner = os.environ.get("PS_VORWAERTS_DIR", os.path.join(HIER, "vorwaerts"))
    logdir = os.environ.get("PS_VORWAERTS_LOG", os.path.join(HIER, "_lernen", "vorwaerts"))
    jetzt = datetime.datetime.utcnow()
    heute = _tag(os.environ["PS_VORWAERTS_HEUTE"]) if os.environ.get("PS_VORWAERTS_HEUTE") else jetzt.date()
    if os.environ.get("PS_VORWAERTS_HEUTE"):                    # nur Tests: Uhrzeit des gedachten Laufs 06:00 UTC
        jetzt = datetime.datetime.combine(heute, datetime.time(6, 0))
    jz = jetzt.strftime("%Y-%m-%dT%H:%M:%SZ")
    if os.environ.get("PS_VORWAERTS_SCHLUSS"):
        e = schluss(ordner, logdir, os.environ["PS_VORWAERTS_SCHLUSS"], heute, jz)
        print(f"Schlussauswertung {e['kennung']}: {e['urteil']} (Ereignisse {e['ereignisse_gewertet']}, verpasst {e['ereignisse_verpasst']})")
    else:
        z = lauf(ordner, logdir, heute, jz, os.environ.get("PS_VORWAERTS_STAND", ""))
        print(f"Vorwärtsregister {z['heute']}: Registrierungen {z['registrierungen']}, aktiv {len(z['aktiv'])}, neue Zeilen {z['neue_zeilen']}, Fehler {len(z['fehler'])}")
        for f in z["fehler"]:
            print("  FEHLER", f["kennung"], "; ".join(f["fehler"]))
        if z["fehler"]:
            sys.exit(1)
