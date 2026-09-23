#!/usr/bin/env python3
import gzip
import io
import json
import os
import urllib.parse
import urllib.request

ID = "treasury_tga"
BASE = "https://api.fiscaldata.treasury.gov/services/api/fiscal_service/v1/accounting/dts/operating_cash_balance"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)

ACCOUNT_TYPES = [
    "Federal Reserve Account",
    "Treasury General Account (TGA)",
    "Treasury General Account (TGA) Closing Balance",
]


def fetch_account_type(account_type):
    params = {
        "filter": "account_type:eq:" + account_type,
        "page[size]": "10000",
        "page[number]": "1",
        "sort": "record_date",
        "fields": "record_date,account_type,close_today_bal,open_today_bal",
    }
    url = BASE + "?" + urllib.parse.urlencode(params, safe="[]:,")
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as resp:
        data = json.loads(resp.read().decode("utf-8"))
    return data["data"]


def to_value(rec):
    for key in ("close_today_bal", "open_today_bal"):
        raw = rec.get(key)
        if raw is not None and raw.strip().lower() != "null":
            try:
                return float(raw)
            except ValueError:
                continue
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
    by_date = {}
    for acct in ACCOUNT_TYPES:
        for rec in fetch_account_type(acct):
            val = to_value(rec)
            if val is None:
                continue
            by_date[rec["record_date"]] = val

    rows = sorted(by_date.items())

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "tga.csv.gz"), rows)

    meta = {
        "tga": {
            "einheit": "Millionen USD",
            "beschreibung": "US Treasury General Account, taeglicher Kassenbestand (Daily Treasury Statement, Table I)",
            "quelle_url": BASE,
            "verdichtung": "keine (bereits taeglich)",
            "verfuegbar_nach_tagen": 1,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
