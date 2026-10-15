#!/usr/bin/env python3
"""BEA-Veroeffentlichungstage: BIP-Schaetzungen (Advance/Second/Third bzw.
Preliminary/Final) und Personal Income and Outlays (PCE-Preisindex). 1 am
Veroeffentlichungstag, sonst 0, jeder Kalendertag ab 1996-01-01 bis heute.
Termine aus dem BEA-Veroeffentlichungsarchiv https://www.bea.gov/news/archive
(Filter nach Produkt-Tag 451 = Gross Domestic Product, 716 = PCE Price Index, 476 = Personal Income; Vereinigung, da je Tag einzelne Releases nur in einem Tag stehen);
Archiv beginnt 1996. Der Termin eines BEA-Release ist im jaehrlichen BEA-
Veroeffentlichungskalender (https://www.bea.gov/news/schedule) im Voraus
oeffentlich. Datum = Datum des Archiveintrags (Ortszeit US-Ost)."""
import datetime, gzip, io, json, os, re, urllib.request

ID = "us_bip_bea_veroeffentlichungstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://www.bea.gov/news/archive?field_related_product_target_id=%d&page=%d"
ROW = re.compile(r'<a href="[^"]*"[^>]*>([^<]+)</a>\s*</td>\s*<td[^>]*><time datetime="([^"]+)"')
START = datetime.date(1996, 1, 1)


def get(u):
    req = urllib.request.Request(u, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def holen(tag):
    rows, p = [], 0
    while p < 60:
        r = ROW.findall(get(BASE % (tag, p)))
        if not r:
            break
        rows += r
        p += 1
    return rows


def tage(rows, ok):
    return {datetime.date.fromisoformat(d[:10]) for t, d in rows
            if ok.match(t.strip())}


def schreiben(path, ev, end):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        d = START
        while d <= end:
            t.write("%s,%d\n" % (d.isoformat(), 1 if d in ev else 0))
            d += datetime.timedelta(days=1)
        t.flush()
    open(path, "wb").write(buf.getvalue())


def main():
    end = datetime.datetime.now(datetime.timezone.utc).date()
    gdp = tage(holen(451), re.compile(r"(?i)^(GDP|Gross Domestic Product)(?!.*(territor|puerto))"))
    pce = tage(holen(716) + holen(476), re.compile(r"(?i)^Personal Income(?! (by|for) )"))
    gdp = {d for d in gdp if START <= d <= end}
    pce = {d for d in pce if START <= d <= end}
    if len(gdp) < 100 or len(pce) < 150:
        raise SystemExit("zu wenige Termine: %d/%d" % (len(gdp), len(pce)))
    schreiben(os.path.join(OUT_DIR, "bip.csv.gz"), gdp, end)
    schreiben(os.path.join(OUT_DIR, "pce.csv.gz"), pce, end)
    pub = "taeglich (Termin im jaehrlichen BEA-Veroeffentlichungskalender im Voraus oeffentlich, https://www.bea.gov/news/schedule)"
    def m(txt, n):
        return {"einheit": "Indikator (0/1)", "beschreibung": txt, "quelle_url": "https://www.bea.gov/news/archive",
                "verdichtung": "keine (ein Termin je Kalendertag aus dem BEA-Archiv)", "publikation": pub,
                "verfuegbar_nach_tagen": 0, "revidiert": False}
    meta = {"bip": m("1 am Veroeffentlichungstag einer BEA-BIP-Schaetzung (Advance/Second/Third bzw. Preliminary/Final), sonst 0, ab 1996-01-01.", 0),
            "pce": m("1 am Veroeffentlichungstag von Personal Income and Outlays (PCE-Preisindex, Konsum), sonst 0, ab 1996-01-01.", 0)}
    json.dump(meta, open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8"), ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
