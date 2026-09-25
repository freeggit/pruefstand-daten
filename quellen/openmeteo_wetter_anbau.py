#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "openmeteo_wetter_anbau"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = "2015-01-01"
# Sicherheitsabstand ueber die von Open-Meteo dokumentierte 5-7-Tage-Nachlieferung
# der ERA5-Reanalyse hinaus, damit nur bereits finalisierte (nicht mehr revidierte)
# Tage abgelegt werden (K4).
VERFUEGBAR_NACH_TAGEN = 10

REGIONEN = {
    "mais_guertel": {
        "lat": 41.60,
        "lon": -93.60,
        "beschreibung": "Taegliche Niederschlagssumme US-Maisguertel (Iowa, nahe Des Moines), ERA5-Reanalyse via Open-Meteo",
    },
    "soja_mato_grosso": {
        "lat": -12.90,
        "lon": -56.10,
        "beschreibung": "Taegliche Niederschlagssumme brasilianisches Sojaanbaugebiet (Sorriso, Mato Grosso), ERA5-Reanalyse via Open-Meteo",
    },
    "monsun_indien": {
        "lat": 21.15,
        "lon": 79.09,
        "beschreibung": "Taegliche Niederschlagssumme zentralindisches Monsun-Agrargebiet (Nagpur, Maharashtra), ERA5-Reanalyse via Open-Meteo",
    },
}


def cutoff_date():
    return (
        datetime.datetime.now(datetime.timezone.utc).date()
        - datetime.timedelta(days=VERFUEGBAR_NACH_TAGEN)
    )


def fetch(lat, lon, end_date):
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        "?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
        "&daily=precipitation_sum&timezone=UTC" % (lat, lon, START, end_date)
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return json.loads(resp.read().decode("utf-8"))


def parse(payload):
    daily = payload.get("daily", {})
    times = daily.get("time", [])
    vals = daily.get("precipitation_sum", [])
    rows = []
    for d, v in zip(times, vals):
        if v is None:
            continue
        rows.append((d, float(v)))
    rows.sort()
    return rows


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    end_date = cutoff_date().isoformat()
    meta = {}
    for reihe, info in REGIONEN.items():
        payload = fetch(info["lat"], info["lon"], end_date)
        rows = parse(payload)
        if not rows:
            raise SystemExit("keine Daten fuer %s" % reihe)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "mm/Tag",
            "beschreibung": info["beschreibung"],
            "quelle_url": "https://archive-api.open-meteo.com/v1/archive",
            "verdichtung": "keine (ERA5-Reanalyse liefert bereits Tageswerte)",
            "verfuegbar_nach_tagen": VERFUEGBAR_NACH_TAGEN,
            "revidiert": False,
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
