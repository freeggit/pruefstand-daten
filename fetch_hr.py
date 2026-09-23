#!/usr/bin/env python3
"""Prüfstand-Datenspiegel, Schicht «hochaufgelöst».
Holt öffentliche Reihen mit Stunden- oder Tagesauflösung und langer Historie für den Suchraum.
Ablage: data/hr/<quelle>/<name>_<jahr>.csv, ein File je Jahr, damit tägliche Läufe nur das
laufende Jahr neu schreiben. Grundsatz wie fetch.py: nichts schätzen, nichts reparieren;
Fehler landen in data/hr/manifest_hr.json, alte Dateien bleiben stehen."""
import csv, io, json, os, sys, time, urllib.request, urllib.parse
from datetime import datetime, timezone, date, timedelta

UA = {"User-Agent": "pruefstand-daten/1.1 (GitHub Actions; public research mirror; contact via github.com/freeggit)"}
OUT = "data/hr"
HEUTE = datetime.now(timezone.utc).date()
JAHR = HEUTE.year
man = {"erzeugt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "reihen": {}}

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
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f); w.writerow(head); w.writerows(rows)

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
        key = f"energie:preis_{land}"; pfad = f"{OUT}/energie/preis_{land}_{{y}}.csv"
        for y in jahre(2015, pfad):
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
        key = f"energie:erzeugung_{land}"; pfad = f"{OUT}/energie/erzeugung_{land}_{{y}}.csv"
        for y in jahre(2015, pfad):
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
        key = f"wetter:{name}"; pfad = f"{OUT}/wetter/{name}_{{y}}.csv"
        for y in jahre(2000, pfad):
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
                pfad = f"{OUT}/pegel/{slug}_{y}.csv"
                alt = {}
                if os.path.exists(pfad):
                    with open(pfad, encoding="utf-8") as f:
                        for r in list(csv.reader(f))[1:]:
                            alt[r[0]] = r[1]
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
        key = f"wiki:{slug}"; pfad = f"{OUT}/wiki/{slug}.csv"
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

if __name__ == "__main__":
    os.makedirs(OUT, exist_ok=True)
    for teil in (energie, wetter, pegel, wiki):
        try:
            teil()
        except Exception as e:  # ein Teil darf die anderen nicht mitreissen
            man["reihen"][f"{teil.__name__}:gesamt"] = {"fehler": str(e)}
    with open(f"{OUT}/manifest_hr.json", "w", encoding="utf-8") as f:
        json.dump(man, f, ensure_ascii=False, indent=1)
    n_err = sum(1 for v in man["reihen"].values() if "fehler" in v)
    print(f"fertig: {len(man['reihen'])} Reihen, {n_err} mit Fehlern")
