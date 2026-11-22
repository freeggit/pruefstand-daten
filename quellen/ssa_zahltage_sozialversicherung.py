#!/usr/bin/env python3
"""US Social Security (OASDI): Zahltage als 0/1-Kalenderreihen, rein
deterministisch aus der veroeffentlichten Regel berechnet (kein externer Abruf,
kein Blick auf Kurse).

Beleg: Federal Register 62 FR 6120 vom 11.2.1997 (FR Doc. 97-3205, 20 CFR
404.1807), https://www.govinfo.gov/content/pkg/FR-1997-02-11/html/97-3205.htm:
- bisherige Leistungsbezueger weiterhin am 3. des Monats;
- Neubezueger mit Antrag ab 1.5.1997 am 2., 3. oder 4. Mittwoch (nach Geburtstag);
- faellt der Zahltag auf Samstag, Sonntag oder einen gesetzlichen Bundesfeiertag,
  wird am ersten vorangehenden Tag gezahlt, der keiner davon ist.
Beginn beider Reihen 1997-06-01 (erste Mittwochszahlungen im Juni 1997); die
3.-des-Monats-Regel ist im Beleg als bestehend genannt, ihr Beginn aber nicht
datiert, darum keine Rueckverlaengerung ohne weiteren Beleg (Zusatz 5).
Nicht modelliert: ausserordentliche, per Executive Order gewaehrte Ruhetage
der Bundesverwaltung (z.B. 24.12. einzelner Jahre); Zahlungsverkehr der Fed
laeuft an diesen Tagen in der Regel weiter."""
import datetime
import gzip
import io
import json
import os

ID = "ssa_zahltage_sozialversicherung"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(1997, 6, 1)
BELEG = "https://www.govinfo.gov/content/pkg/FR-1997-02-11/html/97-3205.htm"


def nth_weekday(y, m, wd, n):
    d = datetime.date(y, m, 1)
    d += datetime.timedelta(days=(wd - d.weekday()) % 7)
    return d + datetime.timedelta(weeks=n - 1)


def last_weekday(y, m, wd):
    d = datetime.date(y + (m == 12), m % 12 + 1, 1) - datetime.timedelta(days=1)
    return d - datetime.timedelta(days=(d.weekday() - wd) % 7)


def observed(d):
    if d.weekday() == 5:
        return d - datetime.timedelta(days=1)
    if d.weekday() == 6:
        return d + datetime.timedelta(days=1)
    return d


def federal_holidays(y):
    h = {
        observed(datetime.date(y, 1, 1)),
        nth_weekday(y, 1, 0, 3),   # MLK Day (Bundesfeiertag seit 1986)
        nth_weekday(y, 2, 0, 3),   # Washington's Birthday
        last_weekday(y, 5, 0),     # Memorial Day
        observed(datetime.date(y, 7, 4)),
        nth_weekday(y, 9, 0, 1),   # Labor Day
        nth_weekday(y, 10, 0, 2),  # Columbus Day
        observed(datetime.date(y, 11, 11)),
        nth_weekday(y, 11, 3, 4),  # Thanksgiving
        observed(datetime.date(y, 12, 25)),
    }
    if y >= 2021:  # Juneteenth, Gesetz vom 17.6.2021, erstmals 18.6.2021 begangen
        h.add(observed(datetime.date(y, 6, 19)))
    # 1.1. des Folgejahres auf Samstag -> begangen am 31.12. dieses Jahres
    h.add(observed(datetime.date(y + 1, 1, 1)))
    return h


HOL = {}


def is_holiday(d):
    if d.year not in HOL:
        HOL[d.year] = federal_holidays(d.year)
    return d in HOL[d.year]


def adjust(d):
    while d.weekday() >= 5 or is_holiday(d):
        d -= datetime.timedelta(days=1)
    return d


def write(name, days, end):
    rows = []
    d = START
    while d <= end:
        rows.append("%s,%d\n" % (d.isoformat(), 1 if d in days else 0))
        d += datetime.timedelta(days=1)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0, filename="") as g:
        g.write(("datum,wert\n" + "".join(rows)).encode())
    with open(os.path.join(OUT_DIR, name + ".csv.gz"), "wb") as f:
        f.write(buf.getvalue())


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    end = datetime.datetime.now(datetime.timezone.utc).date()
    dritter, mittwoch = set(), set()
    y, m = START.year, START.month
    while (y, m) <= (end.year + 1, 1):
        dritter.add(adjust(datetime.date(y, m, 3)))
        for n in (2, 3, 4):
            mittwoch.add(adjust(nth_weekday(y, m, 2, n)))
        y, m = (y + 1, 1) if m == 12 else (y, m + 1)
    write("zahltag_dritter", dritter, end)
    write("zahltag_mittwoch", mittwoch, end)
    pub = ("taeglich (Zahltage folgen einer im Voraus veroeffentlichten Regel, "
           "20 CFR 404.1807 / 62 FR 6120; SSA publiziert jaehrlich den Zahlungskalender im Voraus)")
    gemein = {"einheit": "Indikator (0/1)", "quelle_url": BELEG,
              "verdichtung": "keine (deterministische Kalenderreihe, kein externer Datenabruf)",
              "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub}
    meta = {
        "zahltag_dritter": dict(gemein, beschreibung=(
            "1 am Zahltag der Social-Security-Leistungen fuer Bezueger vor Mai 1997 (3. des Monats, "
            "bei Wochenende oder Bundesfeiertag am vorangehenden Geschaeftstag), sonst 0, je Kalendertag ab 1997-06-01. Status ruhend: 349 von 354 Zahltagen "
            "(98.6%) fallen auf turn_of_month_effekt:turn_of_month (Redundanz).")
            , status="ruhend"),
        "zahltag_mittwoch": dict(gemein, beschreibung=(
            "1 an den Zahltagen fuer Neubezueger ab Mai 1997 (2., 3. und 4. Mittwoch des Monats, bei "
            "Bundesfeiertag am vorangehenden Geschaeftstag), sonst 0, je Kalendertag ab 1997-06-01.")),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
