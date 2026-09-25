#!/usr/bin/env python3
"""US-Wahltag: 1 am 'erster Dienstag nach erstem Montag im November' jedes
geraden Jahres (US-Bundeswahlgesetz, seit 1845 fuer Praesidentschaftswahlen,
seit 1875 einheitlich auch fuer Kongresswahlen; US Code Titel 2 Sec. 7 und
Titel 3 Sec. 1), sonst 0. Rein deterministische Kalenderberechnung, kein
externer Datenabruf noetig (Zusatz 4, E11: Historie weit vor 1990)."""
import datetime
import gzip
import io
import json
import os

ID = "usa_wahltag"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1845, 1, 1)


def election_day(year):
    d = datetime.date(year, 11, 1)
    first_monday_offset = (0 - d.weekday()) % 7
    first_monday = d + datetime.timedelta(days=first_monday_offset)
    return first_monday + datetime.timedelta(days=1)


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def build(end):
    event_days = set()
    for year in range(START.year, end.year + 1):
        if year % 2 != 0:
            continue
        d = election_day(year)
        if START <= d <= end:
            event_days.add(d)
    return [(d, 1 if d in event_days else 0) for d in daterange(START, end)]


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d.isoformat(), v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    rows = build(end)
    gzip_write(os.path.join(OUT_DIR, "wahltag.csv.gz"), rows)

    meta = {
        "wahltag": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am US-Wahltag (erster Dienstag nach erstem Montag im November, jedes gerade Jahr: Kongress- und/oder Praesidentschaftswahl), sonst 0, fuer jeden Kalendertag ab 1845-01-01 (US Code Titel 3 Sec. 1, Praesidentschaftswahltermin seit 1845 gesetzlich fixiert; Kongresswahlen seit 1875 einheitlich auf denselben Tag, US Code Titel 2 Sec. 7).",
            "quelle_url": "kein externer Abruf (deterministische Kalenderberechnung nach US Code Titel 2 Sec. 7 / Titel 3 Sec. 1)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "publikation": "taeglich (Ereignisdatum gesetzlich fixiert und lange im Voraus oeffentlich bekannt, Reihe wird taeglich fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
