#!/usr/bin/env python3
"""B3 Ibovespa: Termine der Neugewichtung (Stichtag) und der ersten/letzten Vorschau, 0/1, ab 2011.

Regel (BM&FBOVESPA-Mitteilung 2011, B3 "Record of Changes to Index Methodologies"):
  Vier-Monats-Zyklen Januar-April, Mai-August, September-Dezember.
  Stichtag (Beginn der Gueltigkeit): bis Mai 2011 erster Handelstag im Januar/Mai/September,
  ab September 2011 erster Montag im Januar/Mai/September, faellt er auf einen Feiertag,
  der naechste Handelstag.
  Vorschauen (seit 2011 unveraendert): 1. am ersten Handelstag des letzten Monats der laufenden
  Carteira (Dezember/April/August), 2. am ersten Handelstag nach dem 15. dieses Monats,
  3. am letzten Handelstag dieses Monats (Beleg Zyklus Sep-Dez 2026: Vorschauen 3.8., 17.8., 31.8.2026; Stichtag 8.9.2026, da 7.9. Feiertag).
Handelstage: Mo-Fr ohne B3-Feiertage (Neujahr, Karneval Mo/Di, Karfreitag, Tiradentes, 1. Mai,
Fronleichnam, 7.9., 12.10., 2.11., 15.11., 20.11. ab 2024, 24.12., 25.12., letzter Werktag des Jahres).
Kein externer Abruf; Termine waren nach Regelwerk im Voraus bekannt.
"""
import datetime, gzip, io, json, os, csv

ID = "b3_ibovespa_rebalancing_termine"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
D = datetime.date
T = datetime.timedelta


def easter(y):
    a = y % 19; b = y // 100; c = y % 100; d = b // 4; e = b % 4; f = (b + 8) // 25
    g = (b - f + 1) // 3; h = (19 * a + b - d - g + 15) % 30; i = c // 4; k = c % 4
    l = (32 + 2 * e + 2 * i - h - k) % 7; m = (a + 11 * h + 22 * l) // 451
    mo = (h + l - 7 * m + 114) // 31; da = (h + l - 7 * m + 114) % 31 + 1
    return D(y, mo, da)


_hol = {}
def holidays(y):
    if y in _hol: return _hol[y]
    e = easter(y)
    h = {D(y, 1, 1), e - T(48), e - T(47), e - T(2), D(y, 4, 21), D(y, 5, 1), e + T(60),
         D(y, 9, 7), D(y, 10, 12), D(y, 11, 2), D(y, 11, 15), D(y, 12, 24), D(y, 12, 25)}
    if y >= 2024: h.add(D(y, 11, 20))
    d = D(y, 12, 31)  # letzter Werktag des Jahres: kein Handel
    while d.weekday() >= 5 or d in h: d -= T(1)
    h.add(d)
    _hol[y] = h
    return h


def bd(d): return d.weekday() < 5 and d not in holidays(d.year)
def next_bd(d):
    while not bd(d): d += T(1)
    return d
def prev_bd(d):
    while not bd(d): d -= T(1)
    return d


def stichtag(y, m):
    d = D(y, m, 1)
    if (y, m) < (2011, 9): return next_bd(d)
    d += T((0 - d.weekday()) % 7)
    return next_bd(d)


def main():
    os.makedirs(OUT, exist_ok=True)
    today = datetime.datetime.now(datetime.timezone.utc).date()
    start = D(2011, 1, 1)
    st, v1, v3 = set(), set(), set()
    for y in range(2011, today.year + 2):
        for m in (1, 5, 9):
            s = stichtag(y, m)
            st.add(s)
            pm, py = (12, y - 1) if m == 1 else (m - 1, y)
            if (py, pm) >= (2010, 12):
                v1.add(next_bd(D(py, pm, 1)))
                nm = D(py + (pm == 12), pm % 12 + 1, 1)
                v3.add(prev_bd(nm - T(1)))
    for name, days in (("stichtag", st), ("erste_vorschau", v1), ("letzte_vorschau", v3)):
        buf = io.BytesIO()
        with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
            t = io.TextIOWrapper(g, encoding="utf-8", newline="")
            w = csv.writer(t, lineterminator="\n"); w.writerow(["datum", "wert"])
            d = start
            while d <= today:
                w.writerow([d.isoformat(), 1 if d in days else 0]); d += T(1)
            t.flush()
        open(os.path.join(OUT, name + ".csv.gz"), "wb").write(buf.getvalue())
    base = {"einheit": "Indikator (0/1)",
            "quelle_url": "https://www.b3.com.br/en_us/market-data-and-indices/indices/broad-indices/ibovespa.htm",
            "verdichtung": "keine (deterministische Kalenderreihe nach B3-Regelwerk, kein externer Abruf)",
            "verfuegbar_nach_tagen": 0, "revidiert": False,
            "publikation": "taeglich (Termine nach veroeffentlichtem B3-Indexregelwerk im Voraus bekannt; Regelwechsel Stichtag erster Montag ab September 2011, BM&FBOVESPA-Mitteilung 2011)"}
    meta = {
        "stichtag": dict(base, beschreibung="1 am ersten Gueltigkeitstag der neuen Ibovespa-Carteira (Jan/Mai/Sep; bis Mai 2011 erster Handelstag, ab Sep 2011 erster Montag bzw. naechster Handelstag), sonst 0, ab 2011-01-01."),
        "erste_vorschau": dict(base, beschreibung="1 am Tag der ersten Vorschau (erster Handelstag im Dezember/April/August), sonst 0, ab 2011-01-01."),
        "letzte_vorschau": dict(base, beschreibung="1 am Tag der dritten und letzten Vorschau = letzter Handelstag im Dezember/April/August, sonst 0, ab 2011-01-01."),
    }
    json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), ensure_ascii=False, indent=2)


if __name__ == "__main__":
    main()
