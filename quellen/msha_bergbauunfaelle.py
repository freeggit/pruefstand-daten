#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.request
import zipfile

ID = "msha_bergbauunfaelle"
URL = "https://arlweb.msha.gov/opengovernmentdata/DataSets/Accidents.zip"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)


def fetch_bytes(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return resp.read()
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


def parse_mmddyyyy(s):
    s = s.strip('"').strip()
    if not s:
        return None
    mm, dd, yy = s.split("/")
    return datetime.date(int(yy), int(mm), int(dd))


def main():
    raw = fetch_bytes(URL)
    z = zipfile.ZipFile(io.BytesIO(raw))
    name = z.namelist()[0]

    counts_all = {}
    counts_fatal = {}
    with z.open(name) as fraw:
        f = io.TextIOWrapper(fraw, encoding="latin-1", newline="")
        header = f.readline().rstrip("\r\n").split("|")
        idx_dt = header.index("ACCIDENT_DT")
        idx_deg = header.index("DEGREE_INJURY")
        for line in f:
            parts = line.rstrip("\r\n").split("|")
            if len(parts) <= max(idx_dt, idx_deg):
                continue
            try:
                dt = parse_mmddyyyy(parts[idx_dt])
            except ValueError:
                dt = None
            if dt is None:
                continue
            iso = dt.isoformat()
            counts_all[iso] = counts_all.get(iso, 0) + 1
            if "FATAL" in parts[idx_deg].strip('"').upper():
                counts_fatal[iso] = counts_fatal.get(iso, 0) + 1

    if not counts_all:
        raise RuntimeError("keine MSHA-Unfaelle gefunden")

    first_day = min(datetime.date.fromisoformat(k) for k in counts_all)
    last_event = max(datetime.date.fromisoformat(k) for k in counts_all)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    last_day = min(last_event, today)

    def build_rows(counts):
        rows = []
        cur = first_day
        while cur <= last_day:
            iso = cur.isoformat()
            rows.append((iso, counts.get(iso, 0)))
            cur += datetime.timedelta(days=1)
        return rows

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "gesamt.csv.gz"), build_rows(counts_all))
    gzip_write(os.path.join(OUT_DIR, "fatal.csv.gz"), build_rows(counts_fatal))

    publikation_beleg = (
        "verzoegert: Betreiber muessen Unfaelle nach 30 CFR 50.20 innerhalb "
        "von 10 Arbeitstagen melden (toedliche/schwere Unfaelle sofort "
        "telefonisch), der oeffentliche Datensatz wird von der MSHA regelmaessig "
        "aktualisiert (juengster Wert im Abruf lag 6 Tage zurueck); "
        "verfuegbar_nach_tagen konservativ auf 10 gesetzt, um die maximale "
        "Meldefrist abzudecken"
    )
    revidiert_hinweis = (
        "einzelne Unfaelle koennen mit Verzug bis zur gesetzlichen Meldefrist "
        "nachgetragen werden; bereits erfasste Datensaetze (Unfalldatum, "
        "Schweregrad) werden im Zuge der Untersuchung selten nachtraeglich "
        "korrigiert, Aenderungen an sehr alten Tagen sind nicht zu erwarten"
    )
    meta = {
        "gesamt": {
            "einheit": "Anzahl Unfaelle",
            "beschreibung": (
                "Taegliche Anzahl bei der US-Bergbauaufsicht MSHA gemeldeter "
                "Unfaelle/Verletzungen in US-Bergwerken und -Aufbereitungsanlagen "
                "(Form 7000-1, Accident Injuries Data Set), Datum = ACCIDENT_DT "
                "(Unfalltag), 0 an Tagen ohne Meldung"
            ),
            "quelle_url": "https://www.msha.gov/data-and-reports/data-sources-and-calculators/data-resources/mdsrg/accident-injuries-and-illnesses-data-set",
            "verdichtung": "Anzahl Unfaelle je Kalendertag (ACCIDENT_DT)",
            "publikation": publikation_beleg,
            "verfuegbar_nach_tagen": 10,
            "revidiert": revidiert_hinweis,
        },
        "fatal": {
            "einheit": "Anzahl toedliche Unfaelle",
            "beschreibung": (
                "Taegliche Anzahl toedlicher MSHA-Bergbauunfaelle "
                "(DEGREE_INJURY enthaelt 'FATAL'), Teilmenge von gesamt; "
                "Datum = ACCIDENT_DT"
            ),
            "quelle_url": "https://www.msha.gov/data-and-reports/data-sources-and-calculators/data-resources/mdsrg/accident-injuries-and-illnesses-data-set",
            "verdichtung": "Anzahl toedliche Unfaelle je Kalendertag (ACCIDENT_DT)",
            "publikation": publikation_beleg,
            "verfuegbar_nach_tagen": 10,
            "revidiert": revidiert_hinweis,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
