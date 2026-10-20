#!/usr/bin/env python3
"""VIX-Verfall: Schlusskurs-Abrechnungstag der monatlichen VIX-Futures/-Optionen.

Regel (Cboe Futures Exchange, Rulebook, Kontraktspezifikation VX): Abrechnung am
Mittwoch, der 30 Tage vor dem dritten Freitag des FOLGEMONATS liegt.
Feiertagsregel, zwei Fassungen der Cboe-Regelwerkseinreichungen bei der CFTC:
- aeltere Fassung (SR-CFE-2011-031, 2011; SR-CFE-2014-020): ist der dritte Freitag
  ein Cboe-Feiertag, gilt 30 Tage vor dem davorliegenden Cboe-Geschaeftstag.
- neuere Fassung (CFTC-Einreichung cfedcm001 vom 21.12.2021): ist der Mittwoch oder
  der Freitag 30 Tage nach dem Mittwoch ein Feiertag, gilt der Geschaeftstag vor dem Mittwoch.
Angewandt: aeltere Fassung bis Verfall 2021-12-31, neuere ab 2022-01-01 (Umstellungstag
nicht einzeln belegt). Start 2011-01-01 (frueheste hier belegte Regelfassung).
Termine sind Jahre im Voraus bekannt. Feiertage: Schwesterquelle us_boersenfeiertage.
"""
import datetime, gzip, importlib.util, io, json, os

ID = "vix_verfall_termine"
HERE = os.path.dirname(os.path.abspath(__file__))
OUT_DIR = os.path.join(HERE, "..", "data", "neu", ID)
START = datetime.date(2011, 1, 1)
D = datetime.timedelta


def load_closed(end):
    spec = importlib.util.spec_from_file_location("usbf", os.path.join(HERE, "us_boersenfeiertage.py"))
    m = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(m)
    return m.build_closure_days(end + D(days=400))


def third_friday(y, m):
    d = datetime.date(y, m, 1)
    return d + D(days=(4 - d.weekday()) % 7 + 14)


def prev_bday(d, closed):
    d -= D(days=1)
    while d.weekday() >= 5 or d in closed:
        d -= D(days=1)
    return d


def settlement(y, m, closed):
    """Verfallstag des Kontrakts mit Ablaufmonat (y, m)."""
    ny, nm = (y + 1, 1) if m == 12 else (y, m + 1)
    fri = third_friday(ny, nm)
    wed = fri - D(days=30)
    if y >= 2022:
        if wed in closed or fri in closed:
            return prev_bday(wed, closed)
        return wed
    if fri in closed:
        return prev_bday(fri, closed) - D(days=30)
    return wed


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    closed = load_closed(end)
    ev = set()
    for y in range(START.year, end.year + 1):
        for m in range(1, 13):
            s = settlement(y, m, closed)
            if START <= s <= end:
                ev.add(s)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        d = START
        while d <= end:
            t.write("%s,%d\n" % (d.isoformat(), 1 if d in ev else 0))
            d += D(days=1)
        t.flush()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "verfall.csv.gz"), "wb") as f:
        f.write(buf.getvalue())
    meta = {"verfall": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Abrechnungstag der monatlichen VIX-Futures und -Optionen (Mittwoch 30 Tage vor dem dritten Freitag des Folgemonats, mit Feiertagsregel), sonst 0.",
        "quelle_url": "https://cdn.cboe.com/resources/regulation/rule_filings/approved/2011/SR-CFE-2011-031.pdf ; https://cftc.gov/filings/ptc/ptc122121cfedcm001.pdf",
        "verdichtung": "keine (deterministische Kalenderreihe)",
        "publikation": "taeglich (Verfallstermine folgen aus dem veroeffentlichten Cboe-Regelwerk und sind Jahre im Voraus bekannt)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False}}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
