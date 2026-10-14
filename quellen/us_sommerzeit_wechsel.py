#!/usr/bin/env python3
"""US-Sommerzeit-Wechsel als 0/1-Ereignisreihe, ab 1976.

Regel (Uniform Time Act 1966, Energy Policy Act 2005; 15 U.S.C. 260a, NIST/USNO):
  Beginn: 1976-1986 letzter Sonntag im April; 1987-2006 erster Sonntag im April;
          ab 2007 zweiter Sonntag im Maerz.
  Ende:   1976-2006 letzter Sonntag im Oktober; ab 2007 erster Sonntag im November.
1974/1975 (Sonderregelung Energiekrise, Daten gesetzlich abweichend) und 1967-1973
(Termine je Bundesstaat uneinheitlich) werden nicht erfasst: nichts erfinden.
Wert = 1 am ersten Handelstag (Montag) nach dem Wechsel-Sonntag, sonst 0; kein
externer Abruf, Termine waren gesetzlich im Voraus bekannt.
"""
import datetime, gzip, io, json, os, csv

ID = "us_sommerzeit_wechsel"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)


def sunday(y, m, n):  # n-tes Sonntag, n=-1 letzter
    if n > 0:
        d = datetime.date(y, m, 1)
        d += datetime.timedelta((6 - d.weekday()) % 7 + 7 * (n - 1))
        return d
    d = (datetime.date(y + (m == 12), m % 12 + 1, 1)) - datetime.timedelta(1)
    return d - datetime.timedelta((d.weekday() - 6) % 7)


def events(y):
    if y <= 1986: b = sunday(y, 4, -1)
    elif y <= 2006: b = sunday(y, 4, 1)
    else: b = sunday(y, 3, 2)
    e = sunday(y, 10, -1) if y <= 2006 else sunday(y, 11, 1)
    return b + datetime.timedelta(1), e + datetime.timedelta(1)


def write(name, days, start, end):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        t = io.TextIOWrapper(g, encoding="utf-8", newline="")
        w = csv.writer(t, lineterminator="\n"); w.writerow(["datum", "wert"])
        d = start
        while d <= end:
            w.writerow([d.isoformat(), 1 if d in days else 0]); d += datetime.timedelta(1)
        t.flush()
    open(os.path.join(OUT, name + ".csv.gz"), "wb").write(buf.getvalue())


def main():
    os.makedirs(OUT, exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    ev = [events(y) for y in range(1976, today.year + 1)]
    start = datetime.date(1976, 1, 1)
    write("beginn", {b for b, _ in ev}, start, today)
    write("ende", {e for _, e in ev}, start, today)
    base = {"einheit": "Indikator (0/1)", "quelle_url": "https://www.nist.gov/pml/time-and-frequency-division/popular-links/daylight-saving-time-dst",
            "verdichtung": "keine (deterministische Kalenderreihe, kein externer Abruf)", "verfuegbar_nach_tagen": 0, "revidiert": False,
            "publikation": "taeglich (Termin gesetzlich im Voraus bekannt: Uniform Time Act 1966, Energy Policy Act 2005)"}
    meta = {"beginn": dict(base, beschreibung="1 am ersten Handelstag (Montag) nach Beginn der US-Sommerzeit, sonst 0, ab 1976-01-01 (Regel: 1976-86 letzter So April, 1987-2006 erster So April, ab 2007 zweiter So Maerz)."),
            "ende": dict(base, beschreibung="1 am ersten Handelstag (Montag) nach Ende der US-Sommerzeit, sonst 0, ab 1976-01-01 (1976-2006 letzter So Oktober, ab 2007 erster So November).")}
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
