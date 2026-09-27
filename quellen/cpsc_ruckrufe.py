#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "cpsc_ruckrufe"
BASE = "https://www.saferproducts.gov/RestWebServices/Recall"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
FIRST_YEAR = 1973  # Gruendungsjahr der CPSC, erste Faelle im API-Bestand


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


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    counts = {}
    for year in range(FIRST_YEAR, today.year + 1):
        start = "%d-01-01" % year
        end_date = min(datetime.date(year, 12, 31), today)
        end = end_date.isoformat()
        url = BASE + "?" + urllib.parse.urlencode(
            {"format": "json", "RecallDateStart": start, "RecallDateEnd": end}
        )
        try:
            data = fetch(url)
        except Exception:
            continue
        for rec in data or []:
            rd = rec.get("RecallDate")
            if not rd or len(rd) < 10:
                continue
            iso = rd[:10]
            try:
                datetime.date.fromisoformat(iso)
            except ValueError:
                continue
            counts[iso] = counts.get(iso, 0) + 1

    if not counts:
        raise RuntimeError("keine Ruckrufe gefunden")

    first_day = min(datetime.date.fromisoformat(k) for k in counts)
    last_event = max(datetime.date.fromisoformat(k) for k in counts)
    last_day = min(max(last_event, today), today)

    rows = []
    cur = first_day
    while cur <= last_day:
        iso = cur.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        cur += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "ruckrufe.csv.gz"), rows)

    meta = {
        "ruckrufe": {
            "einheit": "Anzahl Ruckrufe",
            "beschreibung": (
                "Taegliche Anzahl von Produktrueckrufen der US-Verbraucherschutzbehoerde "
                "CPSC (Consumer Product Safety Commission, SaferProducts.gov RestWebService), "
                "Datum = RecallDate (Tag der oeffentlichen Bekanntgabe), 0 an Tagen ohne "
                "Ruckruf. Umfasst alle Produktkategorien (u.a. Spielzeug, Haushaltsgeraete, "
                "Sportartikel, Kinderausstattung) -- Mechanismus zyklischer/nichtzyklischer "
                "Konsum (XLY, XLP) und Produkthaftungsrisiko."
            ),
            "quelle_url": "https://www.saferproducts.gov/RestWebServices/Recall",
            "verdichtung": "Anzahl Ruckrufe je Kalendertag (RecallDate)",
            "publikation": (
                "taeglich: CPSC veroeffentlicht Ruckrufe am Tag der Bekanntgabe auf "
                "cpsc.gov/Recalls, das RecallDate der API entspricht diesem Tag "
                "(beobachtet: juengste Eintraege im Abruf lagen wenige Tage zurueck)"
            ),
            "verfuegbar_nach_tagen": 2,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
