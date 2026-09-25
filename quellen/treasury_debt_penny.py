#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "treasury_debt_penny"
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v2/accounting/od/debt_to_penny"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

FIELDS = ["tot_pub_debt_out_amt", "debt_held_public_amt", "intragov_hold_amt"]
REIHEN = {
    "tot_pub_debt_out_amt": "gesamt",
    "debt_held_public_amt": "oeffentlich_gehalten",
    "intragov_hold_amt": "intragovernmental",
}
BESCHREIBUNG = {
    "gesamt": "Gesamte ausstehende Bundesschuld der USA (Debt to the Penny, Total Public Debt Outstanding)",
    "oeffentlich_gehalten": "US-Bundesschuld, vom Publikum gehaltener Anteil (Debt Held by the Public)",
    "intragovernmental": "US-Bundesschuld, regierungsinterner Anteil (Intragovernmental Holdings)",
}


def fetch_all():
    params = {
        "fields": "record_date," + ",".join(FIELDS),
        "sort": "record_date",
        "page[size]": "10000",
    }
    url = BASE + "?" + urllib.parse.urlencode(params, safe="[]:,")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=60) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["data"]


def to_value(raw):
    if raw is None:
        return None
    s = raw.strip()
    if not s or s.lower() == "null":
        return None
    try:
        return float(s)
    except ValueError:
        return None


def gzip_write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        text = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        text.write("datum,wert\n")
        for d, v in rows:
            text.write("%s,%s\n" % (d, v))
        text.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    records = fetch_all()
    by_field = {field: [] for field in FIELDS}
    for rec in records:
        d = rec["record_date"]
        for field in FIELDS:
            v = to_value(rec.get(field))
            if v is not None:
                by_field[field].append((d, v))

    os.makedirs(OUT_DIR, exist_ok=True)
    meta = {}
    for field, rows in by_field.items():
        reihe = REIHEN[field]
        if not rows:
            continue
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        meta[reihe] = {
            "einheit": "USD",
            "beschreibung": BESCHREIBUNG[reihe],
            "quelle_url": BASE,
            "verdichtung": "keine (bereits taeglich, Bankarbeitstage)",
            "publikation": "taeglich (Fiscal Data API 'Debt to the Penny', Aktualisierung am naechsten Geschaeftstag)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }

    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
