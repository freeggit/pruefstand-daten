#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

ID = "openmeteo_wetter_anbau"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = "1940-01-01"  # Zusatz 4 (E11): fruehestes von Open-Meteo erlaubtes Archivdatum
# Sicherheitsabstand ueber die von Open-Meteo dokumentierte 5-7-Tage-Nachlieferung
# der ERA5-Reanalyse hinaus, damit nur bereits finalisierte (nicht mehr revidierte)
# Tage abgelegt werden (K4).
VERFUEGBAR_NACH_TAGEN = 5

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


# Inkrementeller Abruf (Lernrunde 2026-11-20): Open-Meteo gewichtet Anfragen
# nach Datenmenge; der volle Bereich ab 1940 (rund 31'700 Tage je Region)
# loeste wiederholt HTTP 429 aus. Liegt eine Datei vor, wird nur ab
# letztem Datum minus UEBERLAPPUNG_TAGE neu geholt und zusammengefuehrt.
UEBERLAPPUNG_TAGE = 30


def read_existing(path):
    if not os.path.exists(path):
        return []
    rows = []
    with gzip.open(path, "rt", encoding="utf-8") as f:
        next(f, None)
        for line in f:
            line = line.strip()
            if not line:
                continue
            d, v = line.split(",", 1)
            rows.append((d, float(v)))
    return rows


def fetch(lat, lon, end_date, start_date=START):
    url = (
        "https://archive-api.open-meteo.com/v1/archive"
        "?latitude=%s&longitude=%s&start_date=%s&end_date=%s"
        "&daily=precipitation_sum&timezone=UTC" % (lat, lon, start_date, end_date)
    )
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    # Retry mit Backoff bei 429 (Rate-Limit auf geteilter IP) und bei
    # vorübergehenden Netzwerk-/TLS-Zeitüberschreitungen (URLError/Timeout);
    # kein Umgehen einer Sperre, nur Abwarten wie von der API erwartet.
    # Lernrunde 2026-11-22: Retry-After der API beachten (hoechstens 90 s).
    verzoegerungen = (5, 15, 30)
    letzter_fehler = None
    wartezeit = 0
    for i in range(len(verzoegerungen) + 1):
        if wartezeit:
            time.sleep(wartezeit)
        try:
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            letzter_fehler = e
            if e.code != 429:
                raise
            wartezeit = verzoegerungen[min(i, len(verzoegerungen) - 1)]
            try:
                wartezeit = min(90, max(wartezeit, int(e.headers.get("Retry-After") or 0)))
            except (TypeError, ValueError):
                pass
        except urllib.error.URLError as e:
            letzter_fehler = e
            wartezeit = verzoegerungen[min(i, len(verzoegerungen) - 1)]
    raise letzter_fehler


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
    fehler = []
    abgerufen = 0
    for reihe, info in REGIONEN.items():
        pfad = os.path.join(OUT_DIR, reihe + ".csv.gz")
        alt = read_existing(pfad)
        start = START
        # Lernrunde 2026-11-22: Der Scout laeuft alle 4 Stunden, ERA5 waechst
        # nur taeglich. Ist der Bestand schon bis end_date nachgefuehrt, wird
        # nicht abgefragt (weniger Anfragen, weniger HTTP 429 auf der
        # geteilten IP). Faellt eine Region aus, bleibt ihr Bestand erhalten
        # und die anderen Regionen laufen weiter; der Fehler wird am Ende
        # gemeldet.
        if alt and alt[-1][0] >= end_date:
            neu = []
        else:
            if alt:
                letzte = datetime.date.fromisoformat(alt[-1][0])
                start = max(
                    datetime.date.fromisoformat(START),
                    letzte - datetime.timedelta(days=UEBERLAPPUNG_TAGE),
                ).isoformat()
            if abgerufen:
                time.sleep(3)
            abgerufen += 1
            try:
                neu = parse(fetch(info["lat"], info["lon"], end_date, start))
            except Exception as e:  # noqa: BLE001
                if not alt:
                    raise
                fehler.append("%s: %s" % (reihe, e))
                neu = []
        if not neu and not alt:
            raise SystemExit("keine Daten fuer %s" % reihe)
        if neu:
            zusammen = dict(alt)
            zusammen.update(dict(neu))
            gzip_write(pfad, sorted(zusammen.items()))
        meta[reihe] = {
            "einheit": "mm/Tag",
            "beschreibung": info["beschreibung"],
            "quelle_url": "https://archive-api.open-meteo.com/v1/archive",
            "verdichtung": "keine (ERA5-Reanalyse liefert bereits Tageswerte)",
            "publikation": 'verzoegert (ERA5-Reanalyse; Zusatz 5 (25.9.2026) setzt verfuegbar_nach_tagen fest auf 5 Tage fuer Reanalyse-Wetterreihen)',
            "verfuegbar_nach_tagen": VERFUEGBAR_NACH_TAGEN,
            "revidiert": False,
        }

    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    if fehler:
        raise RuntimeError("; ".join(fehler))


if __name__ == "__main__":
    main()
