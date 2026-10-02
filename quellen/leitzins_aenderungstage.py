#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import urllib.request

ID = "leitzins_aenderungstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

URL_DFEDTAR = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTAR"
URL_DFEDTARU = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=DFEDTARU"
URL_ECBDFR = "https://fred.stlouisfed.org/graph/fredgraph.csv?id=ECBDFR"


def fetch(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8")


def parse(text):
    rows = []
    for line in text.splitlines()[1:]:
        if not line:
            continue
        d, _, v = line.partition(",")
        v = v.strip()
        if not v or v == ".":
            continue
        try:
            fv = float(v)
        except ValueError:
            continue
        rows.append((d, fv))
    rows.sort()
    return rows


def change_days(rows):
    out = []
    prev = None
    for d, v in rows:
        flag = 1 if (prev is not None and v != prev) else 0
        out.append((d, flag))
        prev = v
    return out


# Zusatz 5 (25.9.2026): vor dem 4.2.1994 gab das FOMC Zielsatzaenderungen nicht
# am Entscheidtag bekannt (erste zeitgleiche Bekanntgabe: Sitzung vom 4.2.1994);
# vorherige Aenderungen wurden vom Markt erst mit Verzug aus Open-Market-Operationen
# erschlossen. Ohne belegtes frueheres Bekanntgabedatum je Termin faellt die Reihe
# vor diesem Datum weg (K4/Zusatz 5).
FOMC_CUTOFF = "1994-02-04"


# Korrektur 2.10.2026 (Datenaudit): DFEDTARU wechselt meist erst am Tag der WIRKSAMKEIT (Tag nach
# der Bekanntgabe, z.B. Statement 15.3.2017, "effective March 16, 2017"). Die Reihe soll den Tag der
# Bekanntgabe markieren. Regel: ist der Wechseltag selbst kein FOMC-Entscheidtag, der Kalendertag
# davor aber schon (Reihe kalender_ereignisse/fomc_sitzung), gilt der Entscheidtag. Ausserplanmaessige
# Entscheide einzeln belegt (https://www.federalreserve.gov/monetarypolicy/fomchistorical2020.htm).
AUSSERPLANMAESSIG = {"2020-03-04": "2020-03-03", "2020-03-16": "2020-03-15"}
FOMC_SITZUNG = os.path.join(os.path.dirname(__file__), "..", "data", "neu", "kalender_ereignisse", "fomc_sitzung.csv.gz")


def entscheidtage():
    tage = set()
    with gzip.open(FOMC_SITZUNG, "rt", encoding="utf-8") as f:
        next(f)
        for line in f:
            d, _, v = line.strip().partition(",")
            if v and float(v) == 1:
                tage.add(d)
    if not tage:
        raise SystemExit("keine FOMC-Entscheidtage in %s" % FOMC_SITZUNG)
    return tage


def auf_bekanntgabe(flags, sitzung):
    verschoben, nicht_zugeordnet = {}, []
    for d, v in flags:
        if not v or d < "2008-12-17":
            continue
        if d in AUSSERPLANMAESSIG:
            verschoben[d] = AUSSERPLANMAESSIG[d]
        elif d not in sitzung:
            vortag = (datetime.date.fromisoformat(d) - datetime.timedelta(days=1)).isoformat()
            if vortag in sitzung:
                verschoben[d] = vortag
            else:
                nicht_zugeordnet.append(d)
    ziel = set(verschoben.values())
    out = [(d, 0 if d in verschoben else (1 if d in ziel else v)) for d, v in flags]
    fehlend = ziel - {d for d, _ in flags}
    if fehlend:
        raise SystemExit("Entscheidtag fehlt in der Tagesreihe: %s" % sorted(fehlend))
    return out, verschoben, nicht_zugeordnet


VERSCHOBEN, NICHT_ZUGEORDNET = {}, []


def build_fomc():
    pre = parse(fetch(URL_DFEDTAR))
    post = parse(fetch(URL_DFEDTARU))
    combined = pre + post
    combined.sort()
    flags = change_days(combined)
    flags, verschoben, offen = auf_bekanntgabe(flags, entscheidtage())
    VERSCHOBEN.update(verschoben); NICHT_ZUGEORDNET.extend(offen)
    return [(d, v) for d, v in flags if d >= FOMC_CUTOFF]


def build_ezb():
    rows = parse(fetch(URL_ECBDFR))
    return change_days(rows)


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
    fomc_rows = build_fomc()
    ezb_rows = build_ezb()
    if not fomc_rows or not ezb_rows:
        raise SystemExit("keine Daten")

    gzip_write(os.path.join(OUT_DIR, "fomc.csv.gz"), fomc_rows)
    gzip_write(os.path.join(OUT_DIR, "ezb.csv.gz"), ezb_rows)

    meta = {
        "fomc": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Tag, an dem sich das von der Fed gesetzte Leitzins-Zielband gegenueber dem Vortag aendert (abgeleitet aus den taeglichen FRED-Reihen DFEDTAR bis 2008-12-15, danach DFEDTARU), sonst 0. Erfasst nur tatsaechliche Zielsatzaenderungen, nicht jede FOMC-Sitzung mit Halte-Entscheid. Beginnt erst am 1994-02-04 (Zusatz 5): davor wurden Zielsatzaenderungen nicht am Entscheidtag bekanntgegeben.",
            "quelle_url": URL_DFEDTARU,
            "verdichtung": "keine (bereits taeglich, Aenderungsindikator aus taeglicher Zielsatzreihe abgeleitet)",
            "publikation": 'taeglich (Entscheiddatum am Tag der Bekanntgabe oeffentlich, Reihe wird taeglich fortgeschrieben)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "auf_bekanntgabetag_verschoben": VERSCHOBEN,
            "nicht_zugeordnet": NICHT_ZUGEORDNET,
            "hinweis_bekanntgabe": "Ab 17.12.2008 (DFEDTARU) wird ein Wechsel am Tag der Wirksamkeit auf den FOMC-Entscheidtag davor gelegt; Datenaudit 1.10.2026",
        },
        "ezb": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Tag, an dem sich der EZB-Einlagensatz (ECBDFR) gegenueber dem Vortag aendert, sonst 0. Erfasst nur tatsaechliche Satzaenderungen, nicht jede EZB-Ratssitzung mit Halte-Entscheid.",
            "quelle_url": URL_ECBDFR,
            "verdichtung": "keine (bereits taeglich, Aenderungsindikator aus taeglicher Zinsreihe abgeleitet)",
            "publikation": 'taeglich (Entscheiddatum am Tag der Bekanntgabe oeffentlich, Reihe wird taeglich fortgeschrieben)',
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
