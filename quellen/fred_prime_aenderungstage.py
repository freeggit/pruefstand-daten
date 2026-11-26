#!/usr/bin/env python3
"""Aenderungstage der US-Bank-Prime-Rate (FRED DPRIME, Fed H.15) als Ereignisreihen.

aenderung: 1 an Beobachtungstagen, an denen DPRIME vom vorigen Beobachtungswert abweicht, sonst 0.
richtung: +1 Erhoehung, -1 Senkung, 0 keine Aenderung.
Erster Beobachtungstag wird nicht ausgegeben (kein Vorwert). Nichts aufgefuellt.
"""
import gzip, io, json, os, urllib.request

ID = "fred_prime_aenderungstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
URL = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DPRIME"


def fetch():
    req = urllib.request.Request(URL, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    rows = []
    for line in text.splitlines()[1:]:
        d, _, v = line.partition(",")
        v = v.strip()
        if not d or not v or v == ".":
            continue
        try:
            rows.append((d.strip(), float(v)))
        except ValueError:
            continue
    rows.sort()
    out = []
    for d, v in rows:
        if out and out[-1][0] == d:
            continue
        out.append((d, v))
    return out


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%d\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    rows = parse(fetch())
    if len(rows) < 1000:
        raise SystemExit("zu wenige Daten")
    aend, richt = [], []
    for (d0, v0), (d1, v1) in zip(rows, rows[1:]):
        diff = round(v1 - v0, 4)
        aend.append((d1, 1 if diff != 0 else 0))
        richt.append((d1, 0 if diff == 0 else (1 if diff > 0 else -1)))
    gzip_write(os.path.join(OUT_DIR, "aenderung.csv.gz"), aend)
    gzip_write(os.path.join(OUT_DIR, "richtung.csv.gz"), richt)
    pub = ("taeglich (Prime-Rate-Aenderungen der Grossbanken wurden am Tag der Ankuendigung oeffentlich "
           "gemeldet und gelten meist ab dem Folgetag; FRED/H.15 datiert auf den Geltungstag, also nicht vor der "
           "Bekanntgabe; H.15 selbst erscheint werktaeglich, verfuegbar_nach_tagen 1 vorsichtig)")
    common = {
        "quelle_url": URL,
        "verdichtung": "keine (Beobachtungstage von DPRIME, US-Bankarbeitstage; Ereignis = Wert weicht vom vorigen Beobachtungswert ab)",
        "publikation": pub,
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "status": "aktiv",
    }
    meta = {
        "aenderung": dict(common, einheit="0/1 (1 = Ereignistag)",
                          beschreibung="Tag einer Aenderung der US-Bank-Prime-Rate (FRED DPRIME, Fed H.15 'majority of top 25 banks'), ab 1955-08-05. Vor 1994 eigenstaendiges, oeffentlich angekuendigtes Signal der Grossbanken zur Geldpolitik; ab 1994 meist gleichtags mit FOMC-Zielaenderung."),
        "richtung": dict(common, einheit="-1/0/+1 (Senkung/keine/Erhoehung)",
                         beschreibung="Richtung der Aenderung der US-Bank-Prime-Rate am Ereignistag (FRED DPRIME), 0 an Tagen ohne Aenderung, ab 1955-08-05."),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
