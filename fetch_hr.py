#!/usr/bin/env python3
"""Prüfstand-Datenspiegel, Schicht «hochaufgelöst».
Holt öffentliche Reihen mit Stunden- oder Tagesauflösung und langer Historie für den Suchraum.
Ablage: data/hr/<quelle>/<name>_<jahr>.csv, ein File je Jahr, damit tägliche Läufe nur das
laufende Jahr neu schreiben. Grundsatz wie fetch.py: nichts schätzen, nichts reparieren;
Fehler landen in data/hr/manifest_hr.json, alte Dateien bleiben stehen."""
import csv, gzip, io, json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "pruefstand-daten/1.1 (GitHub Actions; public research mirror; contact via github.com/freeggit)"}
OUT = "data/hr"
HEUTE = datetime.now(timezone.utc).date()
JAHR = HEUTE.year
man = {"erzeugt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "reihen": {}}
START = time.time()
BUDGET_MIN = float(os.environ.get("HR_BUDGET_MIN", "35"))   # danach wird gespeichert, der Rest folgt im nächsten Lauf

def zeit_um(key=None):
    if (time.time() - START) / 60 > BUDGET_MIN:
        if key:
            eintrag(key, hinweis=f"Zeitbudget {BUDGET_MIN:.0f} min erschöpft, fehlende Jahre folgen im nächsten Lauf")
        man["zeitbudget_erschoepft"] = True
        return True
    return False

def get(url, tries=3, pause=4):
    last = None
    for i in range(tries):
        try:
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=90) as r:
                return r.read()
        except Exception as e:  # noqa
            last = e
            time.sleep(pause * (i + 1))
    raise last

def schreibe(path, head, rows):
    """Schreibt gzip-komprimiert (.csv.gz, mtime 0 für stabile Bytes); entfernt die alte unkomprimierte Datei."""
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(head); w.writerows(rows)
    with open(path, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(buf.getvalue().encode("utf-8"))
    alt = path[:-3] if path.endswith(".gz") else None
    if alt and os.path.exists(alt):
        os.remove(alt)

def lies(path):
    """Liest .csv.gz oder, für den Übergang, die alte .csv."""
    for p in (path, path[:-3] if path.endswith(".gz") else None):
        if p and os.path.exists(p):
            opener = gzip.open if p.endswith(".gz") else open
            with opener(p, "rt", encoding="utf-8") as f:
                return list(csv.reader(f))[1:]
    return []

def eintrag(key, **kw):
    e = man["reihen"].setdefault(key, {"dateien": [], "zeilen": 0})
    for k, v in kw.items():
        if k == "datei":
            e["dateien"].append(v)
        elif k == "zeilen":
            e["zeilen"] += v
        else:
            e[k] = v

def jahre(start, key_pfad):
    """Jahre, die zu holen sind: fehlende Jahresdateien (Nachholen), das laufende Jahr, im Januar zusätzlich das Vorjahr."""
    out = []
    for y in range(start, JAHR + 1):
        laufend = (y == JAHR) or (y == JAHR - 1 and HEUTE.month == 1)
        if laufend or not os.path.exists(key_pfad.format(y=y)):
            out.append(y)
    return out

# ---------------------------------------------------------------- Energie (Fraunhofer ISE, energy-charts)
ENERGIE_LAENDER = [("ch", "CH"), ("de", "DE-LU")]

def energie():
    for land, zone in ENERGIE_LAENDER:
        # Day-Ahead-Preis stündlich, ab 2015
        key = f"energie:preis_{land}"; pfad = f"{OUT}/energie/preis_{land}_{{y}}.csv.gz"
        for y in reversed(jahre(2015, pfad)):
            if zeit_um(key): break
            rows = []
            try:
                for m in range(1, 13):
                    a = date(y, m, 1)
                    if a > HEUTE: break
                    b = (date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1))
                    b = min(b, HEUTE)
                    j = json.loads(get(f"https://api.energy-charts.info/price?bzn={zone}&start={a}&end={b}"))
                    for t, p in zip(j.get("unix_seconds", []), j.get("price", [])):
                        rows.append([datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "" if p is None else p])
                    time.sleep(0.4)
                rows = sorted({r[0]: r for r in rows}.values())
                if rows:
                    schreibe(pfad.format(y=y), ["zeit_utc", "preis_eur_mwh"], rows)
                    eintrag(key, datei=pfad.format(y=y), zeilen=len(rows), letzte=rows[-1][0], einheit="EUR/MWh", aufloesung="1h", quelle="energy-charts.info")
            except Exception as e:
                eintrag(key, fehler=f"{y}: {e}")
        # Erzeugung und Last nach Typ, stündlich/viertelstündlich, ab 2015
        key = f"energie:erzeugung_{land}"; pfad = f"{OUT}/energie/erzeugung_{land}_{{y}}.csv.gz"
        for y in reversed(jahre(2015, pfad)):
            if zeit_um(key): break
            data, typen = {}, []
            try:
                for m in range(1, 13):
                    a = date(y, m, 1)
                    if a > HEUTE: break
                    b = min(date(y + (m == 12), m % 12 + 1, 1) - timedelta(days=1), HEUTE)
                    j = json.loads(get(f"https://api.energy-charts.info/public_power?country={land}&start={a}&end={b}"))
                    ts = j.get("unix_seconds", [])
                    for pt in j.get("production_types", []):
                        n = pt.get("name", "?")
                        if n not in typen: typen.append(n)
                        for t, v in zip(ts, pt.get("data", [])):
                            data.setdefault(t, {})[n] = v
                    time.sleep(0.4)
                if data:
                    rows = [[datetime.fromtimestamp(t, tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")] + ["" if data[t].get(n) is None else data[t][n] for n in typen] for t in sorted(data)]
                    schreibe(pfad.format(y=y), ["zeit_utc"] + typen, rows)
                    eintrag(key, datei=pfad.format(y=y), zeilen=len(rows), letzte=rows[-1][0], einheit="MW", quelle="energy-charts.info")
            except Exception as e:
                eintrag(key, fehler=f"{y}: {e}")

# ---------------------------------------------------------------- Wetter (Open-Meteo, Reanalyse ERA5)
ORTE = [
    ("zuerich", 47.37, 8.54), ("basel", 47.56, 7.59), ("frankfurt", 50.11, 8.68),
    ("kaub", 50.09, 7.76), ("houston", 29.76, -95.37), ("chicago", 41.88, -87.63),
]
WETTER_VAR = "temperature_2m,precipitation,wind_speed_10m,cloud_cover"

def wetter():
    for name, lat, lon in ORTE:
        key = f"wetter:{name}"; pfad = f"{OUT}/wetter/{name}_{{y}}.csv.gz"
        for y in reversed(jahre(2000, pfad)):     # jüngste Jahre zuerst
            if zeit_um(key): break
            a = date(y, 1, 1); b = min(date(y, 12, 31), HEUTE - timedelta(days=6))
            if b < a: continue
            url = ("https://archive-api.open-meteo.com/v1/archive?" + urllib.parse.urlencode(
                {"latitude": lat, "longitude": lon, "start_date": a, "end_date": b, "hourly": WETTER_VAR, "timezone": "UTC"}))
            try:
                h = json.loads(get(url))["hourly"]
                var = WETTER_VAR.split(",")
                rows = [[t + ":00Z"] + ["" if h[v][i] is None else h[v][i] for v in var] for i, t in enumerate(h["time"])]
                schreibe(pfad.format(y=y), ["zeit_utc"] + var, rows)
                eintrag(key, datei=pfad.format(y=y), zeilen=len(rows), letzte=rows[-1][0], aufloesung="1h", quelle="open-meteo ERA5",
                        einheiten="°C, mm, km/h, %")
            except Exception as e:
                eintrag(key, fehler=f"{y}: {e}")
            time.sleep(3.0)  # Open-Meteo zählt ein Jahr als ~26 Aufrufe; Grenze 600 pro Minute

# ---------------------------------------------------------------- Rheinpegel (WSV PEGELONLINE), nur 31 Tage verfügbar -> fortschreiben
PEGEL = ["KAUB", "MAXAU", "KÖLN", "DUISBURG-RUHRORT"]

def pegel():
    for st in PEGEL:
        slug = st.lower().replace("ö", "oe")
        key = f"pegel:{slug}"
        try:
            url = f"https://www.pegelonline.wsv.de/webservices/rest-api/v2/stations/{urllib.parse.quote(st)}/W/measurements.json?start=P31D"
            neu = {m["timestamp"]: m["value"] for m in json.loads(get(url))}
            for y in sorted({k[:4] for k in neu}):          # jede Messung in die Datei ihres Jahres
                pfad = f"{OUT}/pegel/{slug}_{y}.csv.gz"
                alt = {r[0]: r[1] for r in lies(pfad)}
                alt.update({k: v for k, v in neu.items() if k[:4] == y})
                rows = sorted(alt.items())
                schreibe(pfad, ["zeit", "wasserstand_cm"], rows)
                eintrag(key, datei=pfad, zeilen=len(rows), letzte=rows[-1][0], aufloesung="15min", quelle="pegelonline.wsv.de",
                        hinweis="Quelle liefert nur 31 Tage; Historie wächst ab Beginn des Spiegels")
        except Exception as e:
            eintrag(key, fehler=str(e))
        time.sleep(0.5)

# ---------------------------------------------------------------- Aufmerksamkeit (Wikipedia-Seitenaufrufe, täglich ab Juli 2015)
ARTIKEL = [
    ("en", "Recession"), ("en", "Inflation"), ("en", "Stock_market_crash"), ("en", "Bitcoin"),
    ("en", "Nvidia"), ("en", "Tesla,_Inc."), ("en", "Oil_price"), ("en", "Heat_wave"),
    ("de", "Rezession"), ("de", "Inflation"), ("de", "Niedrigwasser"),
    ("en", "Nestlé"), ("en", "Novartis"), ("en", "Roche"), ("en", "UBS"),
]

def wiki():
    ende = (HEUTE - timedelta(days=1)).strftime("%Y%m%d")
    for proj, art in ARTIKEL:
        slug = f"{proj}_{art}".lower().replace(",", "").replace(".", "").replace("é", "e")
        key = f"wiki:{slug}"; pfad = f"{OUT}/wiki/{slug}.csv.gz"
        try:
            url = (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/{proj}.wikipedia/all-access/user/"
                   f"{urllib.parse.quote(art, safe='')}/daily/20150701/{ende}")
            items = json.loads(get(url)).get("items", [])
            rows = [[f"{i['timestamp'][:4]}-{i['timestamp'][4:6]}-{i['timestamp'][6:8]}", i["views"]] for i in items]
            if rows:
                schreibe(pfad, ["datum", "aufrufe"], rows)
                eintrag(key, datei=pfad, zeilen=len(rows), erste=rows[0][0], letzte=rows[-1][0], aufloesung="1d", quelle="wikimedia pageviews")
            else:
                eintrag(key, fehler="keine Daten")
        except Exception as e:
            eintrag(key, fehler=str(e))
        time.sleep(0.3)

def umstellen():
    """Einmalig: vorhandene .csv ohne neuen Abruf in .csv.gz umwandeln, damit nichts neu geladen wird."""
    n = 0
    for wurzel, _, dateien in os.walk(OUT):
        for d in dateien:
            if d.endswith(".csv"):
                p = os.path.join(wurzel, d)
                with open(p, encoding="utf-8") as f:
                    r = list(csv.reader(f))
                if r:
                    schreibe(p + ".gz", r[0], r[1:]); n += 1
    if n:
        man["umgestellt_auf_gzip"] = n

def inventar():
    """Manifest aus dem Dateibestand bauen: jede Reihe listet ALLE ihre Jahresdateien, nicht nur die heute geholten."""
    import re
    bestand = {}
    for wurzel, _, dateien in os.walk(OUT):
        for d in sorted(dateien):
            if not d.endswith(".csv.gz"):
                continue
            quelle = os.path.basename(wurzel)
            name = re.sub(r"(_\d{4})?\.csv\.gz$", "", d)
            bestand.setdefault(f"{quelle}:{name}", []).append(os.path.join(wurzel, d))
    for key, dateien in bestand.items():
        e = man["reihen"].setdefault(key, {})
        e["dateien"] = sorted(dateien)
        zeilen, erste, letzte = 0, None, None
        for pf in e["dateien"]:
            r = lies(pf)
            if r:
                zeilen += len(r); erste = erste or r[0][0]; letzte = r[-1][0]
        e.update(zeilen=zeilen, erste=erste, letzte=letzte)

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    umstellen()
    for teil in (pegel, wiki, energie, wetter):   # Pegel zuerst: Quelle hält nur 31 Tage
        try:
            teil()
        except Exception as e:  # ein Teil darf die anderen nicht mitreissen
            man["reihen"][f"{teil.__name__}:gesamt"] = {"fehler": str(e)}
    inventar()
    with open(f"{OUT}/manifest_hr.json", "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    n_err = sum(1 for v in man["reihen"].values() if "fehler" in v)
    print(f"fertig: {len(man['reihen'])} Reihen, {n_err} mit Fehlern")
