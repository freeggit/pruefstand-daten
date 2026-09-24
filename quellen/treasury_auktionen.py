#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.request

ID = "treasury_auktionen"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query"


def fetch_all():
    rows = []
    page = 1
    size = 1000
    while True:
        url = (
            BASE
            + "?fields=auction_date,bid_to_cover_ratio"
            + "&filter=bid_to_cover_ratio:gt:0"
            + "&sort=auction_date"
            + "&page[number]=%d&page[size]=%d" % (page, size)
        )
        req = urllib.request.Request(url, headers={"User-Agent": UA})
        with urllib.request.urlopen(req, timeout=30) as resp:
            payload = json.loads(resp.read().decode("utf-8"))
        rows.extend(payload["data"])
        total_pages = payload["meta"]["total-pages"]
        if page >= total_pages:
            break
        page += 1
    return rows


def aggregate(rows):
    by_day = {}
    for row in rows:
        d = row["auction_date"]
        try:
            v = float(row["bid_to_cover_ratio"])
        except (TypeError, ValueError):
            continue
        by_day.setdefault(d, []).append(v)
    daily = {}
    for d, vals in by_day.items():
        daily[d] = sum(vals) / len(vals)
    return sorted(daily.items())


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    rows = aggregate(fetch_all())
    if not rows:
        raise SystemExit("keine Daten erhalten")

    gzip_write(os.path.join(OUT_DIR, "bid_to_cover.csv.gz"), rows)

    meta = {
        "bid_to_cover": {
            "einheit": "Verhaeltnis (Gebote/Zuteilung)",
            "beschreibung": "Mittleres Bid-to-Cover-Verhaeltnis aller an diesem Tag abgeschlossenen US-Treasury-Auktionen (Bills, Notes, Bonds); Mass fuer die Nachfrage nach neu emittierten US-Staatsanleihen",
            "quelle_url": "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/od/auctions_query",
            "verdichtung": "Mittelwert ueber alle an diesem Kalendertag abgeschlossenen Auktionen (mehrere Wertpapiere/Tag moeglich)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    os.makedirs(OUT_DIR, exist_ok=True)
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
