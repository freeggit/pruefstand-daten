#!/usr/bin/env python3
import calendar
import datetime
import gzip
import io
import json
import os
import re
import urllib.request

ID = "japan_tankan_veroeffentlichung"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

# BoJ-Archivseiten mit "Date"-Spalte (tatsaechliches Veroeffentlichungsdatum, nicht
# der Erhebungsmonat aus dem Dateinamen). Der Ordner "2001" enthaelt trotz seines
# Namens nur 2004-2005 (fruehere Jahre wurden bei einer Site-Umstrukturierung offenbar
# entfernt, keine durchsuchbare Quelle dafuer gefunden); das ist damit die aelteste
# belegte Veroeffentlichung.
ARCHIVE_YEARS = ["2001", "2006", "2011", "2016", "2021", "2026"]
ARCHIVE_URL = "https://www.boj.or.jp/en/statistics/tk/gaiyo/%s/index.htm"

MONTH_ABBR = {m.lower(): i for i, m in enumerate(calendar.month_abbr) if m}


def http_get(url):
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        return resp.read().decode("utf-8", "replace")


def parse_release_dates(html):
    out = []
    for tr in re.findall(r"<tr>(.*?)</tr>", html, re.S):
        tds = re.findall(r"<td[^>]*>(.*?)</td>", tr, re.S)
        if len(tds) < 2:
            continue
        detail_txt = re.sub(r"<[^>]+>", "", tds[1]).strip()
        if "Survey" not in detail_txt:
            continue
        date_txt = re.sub(r"&nbsp;", " ", tds[0])
        date_txt = re.sub(r"\s+", " ", date_txt).strip()
        m = re.match(r"^([A-Za-z]{3,9})\.?\s+(\d{1,2}),\s*(\d{4})$", date_txt)
        if not m:
            continue
        month = MONTH_ABBR.get(m.group(1)[:3].lower())
        if not month:
            continue
        out.append(datetime.date(int(m.group(3)), month, int(m.group(2))))
    return out


def daterange(start, end):
    d = start
    one = datetime.timedelta(days=1)
    while d <= end:
        yield d
        d += one


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

    event_days = set()
    for year in ARCHIVE_YEARS:
        html = http_get(ARCHIVE_URL % year)
        event_days.update(parse_release_dates(html))

    if not event_days:
        raise SystemExit("keine Tankan-Veroeffentlichungstermine gefunden")

    start = min(event_days)
    event_days = {d for d in event_days if start <= d <= end}
    rows = [(d, 1 if d in event_days else 0) for d in daterange(start, end)]
    gzip_write(os.path.join(OUT_DIR, "tankan_veroeffentlichung.csv.gz"), rows)

    meta = {
        "tankan_veroeffentlichung": {
            "einheit": "Indikator (0/1)",
            "beschreibung": (
                "1 am Veroeffentlichungstag des vierteljaehrlichen BoJ-Tankan-Berichts "
                "(Kurzbericht zur Wirtschaftslage, seit 1957 erhoben), sonst 0, fuer "
                "jeden Kalendertag ab %s bis heute. Termine stammen aus den amtlichen "
                "Archivseiten (Spalte 'Date', tatsaechliches Publikationsdatum, nicht "
                "der im Dateinamen kodierte Erhebungsmonat). Der Archivordner '2001' "
                "enthaelt trotz seiner Bezeichnung 'from 2001 to 2005' nur Eintraege ab "
                "2004-04-01; eine durchsuchbare Terminliste fuer 2001-2003 oder frueher "
                "(Bericht existiert seit 1957) wurde nicht gefunden, daher keine laengere "
                "Historie belegt (Zusatz 5, keine Termine erfinden)."
            ) % start.isoformat(),
            "quelle_url": "https://www.boj.or.jp/en/statistics/tk/gaiyo/index.htm",
            "verdichtung": "keine (deterministische Kalenderreihe aus amtlichem Veroeffentlichungsarchiv)",
            "publikation": "taeglich (Veroeffentlichungsdatum wird von der BoJ im Voraus rollierend bekanntgegeben, Reihe wird taeglich fortgeschrieben)",
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        },
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
