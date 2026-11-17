#!/usr/bin/env python3
"""Fristen fuer Form 13F (Positionsmeldungen institutioneller Verwalter), 1979-heute.

Regel: Rule 13f-1 (Exchange Act Section 13(f)), angenommen 15.6.1978 (Release
34-14852, zunaechst jaehrlich), ab Release 34-15461 vom 5.1.1979 (wirksam
5.2.1979) vierteljaehrlich: Meldung "within 45 days after the last day of"
jedes Kalenderquartals (SEC 13F FAQ, https://www.sec.gov/files/divisions/investment/13ffaq.htm).
45 Tage nach 31.3./30.6./30.9./31.12. = 15.5., 14.8., 14.11., 14.2.
Faellt die Frist auf Samstag, Sonntag oder einen US-Bundesfeiertag, gilt der
naechste Werktag (Exchange Act Rule 0-3). Im Fenster der Fristen kann nur
Washington's Birthday (dritter Montag im Februar, Uniform Monday Holiday Act,
ab 1971) eine Frist verschieben; Veterans Day (11.11.) und Memorial Day liegen
nie auf einem verschobenen Fristtag.
Beginn 1979-03-01: erster Termin im belegten Quartalsregime ist der 15.5.1979.
Die jaehrliche Frist 14.2.1979 (Regime 1978) wird nicht aufgenommen.
Ausserordentliche Schliessungen der SEC sind nicht beruecksichtigt (keine belegt).
Reihe: 1 am Fristtag, sonst 0, jeder Kalendertag bis heute (UTC).
"""
import datetime, gzip, io, json, os

ID = "sec_13f_einreichungsfristen"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(1979, 3, 1)


def third_monday_feb(y):
    d = datetime.date(y, 2, 1)
    return d + datetime.timedelta(days=(0 - d.weekday()) % 7 + 14)


def roll(d):
    while d.weekday() >= 5 or (d.month == 2 and d == third_monday_feb(d.year)):
        d += datetime.timedelta(days=1)
    return d


def fristen(end):
    out = set()
    for y in range(1979, end.year + 2):
        for q_end in (datetime.date(y - 1, 12, 31), datetime.date(y, 3, 31),
                      datetime.date(y, 6, 30), datetime.date(y, 9, 30)):
            f = roll(q_end + datetime.timedelta(days=45))
            if START <= f <= end:
                out.add(f)
    return out


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    fr = fristen(end)
    os.makedirs(OUT_DIR, exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        d = START
        while d <= end:
            t.write("%s,%d\n" % (d.isoformat(), 1 if d in fr else 0))
            d += datetime.timedelta(days=1)
        t.flush()
    with open(os.path.join(OUT_DIR, "frist.csv.gz"), "wb") as f:
        f.write(buf.getvalue())
    meta = {"frist": {
        "einheit": "Indikator (0/1)",
        "beschreibung": "1 am Fristtag fuer Form-13F-Meldungen (45 Tage nach Quartalsende: 14.2., 15.5., 14.8., 14.11.; bei Wochenende oder Washington's Birthday naechster Werktag), sonst 0. Quartalsregime ab Release 34-15461 (1979).",
        "quelle_url": "https://www.sec.gov/files/divisions/investment/13ffaq.htm; https://www.sec.gov/rules/final/34-15461.pdf; Exchange Act Rule 0-3",
        "verdichtung": "keine (deterministische Kalenderreihe aus der Fristregel)",
        "publikation": "taeglich (Frist aus Rule 13f-1 im Voraus bekannt; Beleg SEC 13F FAQ und Release 34-15461)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "status": "aktiv"}}
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
