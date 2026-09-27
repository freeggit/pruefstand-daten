#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request

ID = "fdic_bankausfaelle"
BASE = "https://api.fdic.gov/banks/failures"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
# Gesamtbestand (Stand 2026) liegt bei rund 4100 Faellen; ein einzelner Abruf mit
# grossem limit deckt die gesamte Historie ab, keine Paginierung noetig.
# API-Obergrenze: limit muss <= 10000 sein.
LIMIT = 10000


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def parse_faildate(s):
    # Format "M/D/YYYY"
    m, d, y = s.split("/")
    return datetime.date(int(y), int(m), int(d))


def main():
    url = BASE + "?limit=%d&fields=FAILDATE&format=json" % LIMIT
    d = fetch(url)
    data = d.get("data", [])
    if not data:
        raise RuntimeError("keine Bankausfaelle gefunden")

    counts = {}
    for rec in data:
        rd = rec.get("data", {})
        fd = rd.get("FAILDATE")
        if not fd:
            continue
        try:
            dt = parse_faildate(fd)
        except (ValueError, IndexError):
            continue
        iso = dt.isoformat()
        counts[iso] = counts.get(iso, 0) + 1

    if not counts:
        raise RuntimeError("keine gueltigen Datumsangaben")

    first_day = min(datetime.date.fromisoformat(k) for k in counts)
    last_event = max(datetime.date.fromisoformat(k) for k in counts)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    # bis heute zero-fillen: Tage ohne Bankausfall nach dem letzten Ereignis sind
    # echte Nullen (K5 sonst nicht pruefbar), nicht fehlende Daten.
    last_day = max(last_event, today)
    last_day = min(last_day, today)

    rows = []
    cur = first_day
    while cur <= last_day:
        iso = cur.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        cur += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "anzahl.csv.gz"), rows)

    meta = {
        "anzahl": {
            "einheit": "Anzahl Bankausfaelle",
            "beschreibung": (
                "Taegliche Anzahl von US-Bankausfaellen (FDIC BankFind Suite, "
                "Failures and Assistance Transactions), Datum = FAILDATE (amtliches "
                "Schliessungs-/Uebernahmedatum der FDIC), 0 an Tagen ohne Ausfall"
            ),
            "quelle_url": "https://banks.data.fdic.gov/bankfind-suite/failures",
            "verdichtung": "Anzahl Faelle je Kalendertag (FAILDATE)",
            "publikation": (
                "verzoegert: die FDIC veroeffentlicht am Schliessungstag eine "
                "Pressemitteilung, der API-Datenbestand (api.fdic.gov/banks/failures) "
                "wird aber nur in unregelmaessigen Abstaenden aktualisiert (der "
                "Index-Zeitstempel der Antwort lag zuletzt mehrere Wochen zurueck); "
                "konservativ mit Verzoegerung angesetzt"
            ),
            "verfuegbar_nach_tagen": 30,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
