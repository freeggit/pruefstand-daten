#!/usr/bin/env python3
"""NBS China: Veroeffentlichungstage des offiziellen Einkaufsmanagerindex (PMI).

Quelle: amtliche Jahres-Veroeffentlichungskalender des National Bureau of Statistics
("Regular Press Release Calendar of NBS in JJJJ"), jeweils Ende des Vorjahres publiziert.
Reihe = 1 an jedem im Kalender genannten PMI-Termin, sonst 0, fuer jeden Kalendertag
von 2015-01-01 bis heute (keine Zeilen in der Zukunft).
"""
import datetime
import gzip
import html as htmlmod
import io
import json
import os
import re
import urllib.request

ID = "china_pmi_veroeffentlichung"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
ROOT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..")
OUT_DIR = os.path.join(ROOT, "data", "neu", ID)
BASE = "https://www.stats.gov.cn/english/PressRelease/ReleaseCalendar/"
WD = {"Mon": 0, "Tue": 1, "Wed": 2, "Thu": 3, "Fri": 4, "Sat": 5, "Sun": 6}


def get(url):
    last = None
    for _ in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except Exception as e:  # Verbindungsabbrueche kommen vor
            last = e
    raise last


def text(c):
    return htmlmod.unescape(re.sub(r"<[^>]+>", " ", c)).replace("\xa0", " ")


def kalender_links():
    t = get(BASE)
    out = {}
    for h, s in re.findall(r'<a[^>]*href="([^"]+)"[^>]*>(.*?)</a>', t, re.S):
        m = re.search(r"Release Calendar of NBS in (\d{4})", text(s))
        if m:
            out[int(m.group(1))] = BASE + h.lstrip("./")
    return out


def pmi_termine(year, page):
    t = re.sub(r"<(script|style).*?</\1>", "", page, flags=re.S)
    tage = set()
    zeilen = 0
    for tr in re.findall(r"<tr.*?</tr>", t, re.S):
        cells = [text(c) for c in re.findall(r"<t[dh].*?</t[dh]>", tr, re.S)]
        if not cells:
            continue
        titel = " ".join(cells[:2])
        nm = titel.find("Non-manufact")
        if "Purchasing" not in titel or (nm != -1 and nm < titel.find("Purchasing")):
            continue
        zeilen += 1
        # Monatsspalten = Zellen mit Termin (TT/Wochentag) oder Platzhalter "……";
        # Uhrzeit-Zellen (9:30) stehen je nach Jahr in derselben Zeile und zaehlen nicht.
        monate = [c for c in cells if re.search(r"\d{1,2}\s*/?\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)|\u2026", c)]
        if not monate:  # Anmerkungszeile unter der Tabelle
            zeilen -= 1
            continue
        if len(monate) != 12:
            raise ValueError("%d: %d Monatsspalten statt 12" % (year, len(monate)))
        for mi, c in enumerate(monate, start=1):
            for d, w in re.findall(r"(\d{1,2})\s*/?\s*(Mon|Tue|Wed|Thu|Fri|Sat|Sun)", c):
                dt = datetime.date(year, mi, int(d))
                if dt.weekday() != WD[w]:
                    raise ValueError("Wochentag passt nicht: %s %s" % (dt, w))
                tage.add(dt)
    if zeilen == 0 or len(tage) < 10:
        raise ValueError("PMI-Zeile %d unplausibel (%d Zeilen, %d Tage)" % (year, zeilen, len(tage)))
    return tage


def main():
    links = kalender_links()
    if min(links) > 2015:
        raise SystemExit("Kalender 2015 fehlt")
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    tage = set()
    for y in sorted(links):
        if y < 2015 or y > heute.year:
            continue
        tage |= pmi_termine(y, get(links[y]))
    for y in range(2015, heute.year + 1):
        if y not in links:
            raise SystemExit("Kalender %d fehlt" % y)
    start = datetime.date(2015, 1, 1)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        w = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        w.write("datum,wert\n")
        d = start
        while d <= heute:
            w.write("%s,%d\n" % (d.isoformat(), 1 if d in tage else 0))
            d += datetime.timedelta(days=1)
        w.flush()
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "pmi_termin.csv.gz"), "wb") as f:
        f.write(buf.getvalue())
    meta = {
        "pmi_termin": {
            "einheit": "Indikator (0/1)",
            "beschreibung": "1 am Veroeffentlichungstag des offiziellen NBS-Einkaufsmanagerindex China (Industrie; Dienstleistung erscheint am selben Tag), sonst 0, fuer jeden Kalendertag ab 2015-01-01 bis heute. Termine aus den amtlichen Jahreskalendern 'Regular Press Release Calendar of NBS' (je Ende Vorjahr publiziert, also im Voraus bekannt); Veroeffentlichung 9:30 Uhr Peking = 01:30 UTC, vor Handelsbeginn in Europa und den USA. Jahreskalender vor 2015 sind im englischen Archiv nicht vorhanden. Der Kalender nennt die Termine als vorlaeufig; nachtraegliche Verschiebungen sind nicht erfasst.",
            "quelle_url": BASE,
            "verdichtung": "keine (deterministische Kalenderreihe aus amtlichen Jahreskalendern)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
            "publikation": "taeglich (Termine im Jahreskalender des NBS im Voraus veroeffentlicht, z.B. Kalender 2026 publiziert am 26.12.2025)",
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)
    print("Tage", len(tage), "erste", min(tage), "letzte", max(tage))


if __name__ == "__main__":
    main()
