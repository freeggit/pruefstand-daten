#!/usr/bin/env python3
"""Russell-US-Index-Rekonstitution: 1 am jaehrlichen Umsetzungstag, sonst 0.
Regel seit Einfuehrung der jaehrlichen Rekonstitution 1989 (zuvor quartalsweise ab 1984,
halbjaehrlich ab 1987): Umsetzung nach Handelsschluss am letzten Freitag im Juni; faellt
dieser auf den 29. oder 30. Juni, verschiebt sich der Termin auf den vorhergehenden Freitag
(um Naehe zum Quartalsende/Feiertag 4. Juli mit duenner Liquiditaet zu vermeiden). Belegt
u.a. durch FTSE Russell "Russell Reconstitution" (lseg.com/en/ftse-russell/russell-reconstitution)
und "Four Decades of Russell US Indexes Reconstitution".
Rein deterministische Kalenderberechnung, kein externer Datenabruf noetig (Zusatz 4, E11:
Historie weit vor 1990).

Die urspruenglich im Kandidaten vorgesehene S&P-500-Quartalskomponente (dritter Freitag
Maerz/Juni/September/Dezember) wird NICHT als eigene Reihe abgelegt: diese Tage sind bereits
identisch mit kalender_ereignisse:opex_verfall (Quartals-Verfall) und wuerden keine neue
Information liefern (Zusatz 3, Redundanz vermeiden). Siehe katalog.json grund.

Ab 2026 stellt FTSE Russell auf eine halbjaehrliche Rekonstitution um (zusaetzlicher Termin im
Dezember). Der Juni-Termin 2026 (26.6.2026) folgt weiterhin derselben Regel (letzter Freitag im
Juni, kein 29./30.-Sonderfall). Der neue Dezember-Termin liegt nach dem heutigen Datum dieses
Laufs noch in der Zukunft; er wird ergaenzt, sobald die genaue FTSE-Russell-Tagesregel dafuer
mit einer Primaerquelle belegt ist (keine Termine erfinden, K4/Zusatz 5)."""
import datetime
import gzip
import io
import json
import os

ID = "sp500_russell_rebalance_termine"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
START = datetime.date(1989, 1, 1)


def last_friday_of_june(year):
    d = datetime.date(year, 6, 30)
    offset = (d.weekday() - 4) % 7
    d = d - datetime.timedelta(days=offset)
    if d.day in (29, 30):
        d = d - datetime.timedelta(days=7)
    return d


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


def build(end):
    event_days = set()
    for year in range(START.year, end.year + 1):
        d = last_friday_of_june(year)
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
    gzip_write(os.path.join(OUT_DIR, "russell_reconstitution.csv.gz"), rows)

    meta = {
        "russell_reconstitution": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Umsetzungstag der jaehrlichen Russell-US-Index-Rekonstitution (nach Handelsschluss am letzten Freitag im Juni, verschoben auf den vorhergehenden Freitag falls dieser auf den 29. oder 30. Juni faellt), sonst 0, fuer jeden Kalendertag ab 1989-01-01 (Beginn der jaehrlichen Rekonstitution). Quelle: FTSE Russell 'Russell Reconstitution' / 'Four Decades of Russell US Indexes Reconstitution' (lseg.com/en/ftse-russell/russell-reconstitution).",
            "quelle_url": "kein externer Abruf (deterministische Kalenderberechnung nach dokumentierter FTSE-Russell-Regel)",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
            "publikation": "taeglich (Ereignisdatum lange im Voraus oeffentlich bekannt/regelbasiert, Reihe wird taeglich fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
