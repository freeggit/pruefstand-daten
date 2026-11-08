#!/usr/bin/env python3
import csv, datetime, gzip, io, json, os, urllib.request
from concurrent.futures import ThreadPoolExecutor
ID = "occ_optionsvolumen_taeglich"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
URL = "https://marketdata.theocc.com/daily-volume-statistics?reportType=D&format=csv&reportDate=%s"

def month_text(y, m):
    for _ in range(3):
        try:
            req = urllib.request.Request(URL % ("%04d%02d15" % (y, m)), headers={"User-Agent": UA})
            return urllib.request.urlopen(req, timeout=30).read().decode("utf-8", "replace")
        except Exception:
            pass
    raise RuntimeError("Abruf %d-%02d fehlgeschlagen" % (y, m))

def parse(t):
    out = {}
    import re; t = re.split(r"\r?\n\s*\r?\n", t.strip())[0]  # nur erster Abschnitt (Optionen); danach folgt die Futures-Tabelle
    for r in csv.reader(io.StringIO(t)):
        if len(r) < 6 or r[0] == "Date":
            continue
        try:
            d = datetime.datetime.strptime(r[0], "%m/%d/%Y").date().isoformat()
            out[d] = (int(r[1].replace(",", "")), int(r[2].replace(",", "")))
        except ValueError:
            continue
    return out

def write(path, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    b = io.BytesIO()
    with gzip.GzipFile(fileobj=b, mode="wb", mtime=0) as g:
        g.write(("datum,wert\n" + "".join("%s,%s\n" % x for x in rows)).encode())
    open(path, "wb").write(b.getvalue())

today = datetime.date.today()
months = [(y, m) for y in range(2008, today.year + 1) for m in range(1, 13) if (y, m) <= (today.year, today.month)]
with ThreadPoolExecutor(4) as ex:
    texts = list(ex.map(lambda ym: month_text(*ym), months))
data = {}
for t in texts:
    data.update(parse(t))
days = sorted(d for d in data if data[d][0] > 0)  # Boersenschliessungen (Sandy 2012, Trauertage 2018/2025) mit 0 Kontrakten entfallen
write(os.path.join(OUT, "equity.csv.gz"), [(d, data[d][0]) for d in days])
write(os.path.join(OUT, "index_sonstige.csv.gz"), [(d, data[d][1]) for d in days])
common = {"verdichtung": "keine (Tagessumme der gehandelten Kontrakte)", "verfuegbar_nach_tagen": 1, "revidiert": False,
  "quelle_url": "https://www.theocc.com/market-data/market-data-reports/volume-reports/daily-volume",
  "publikation": "taeglich (OCC veroeffentlicht das Tagesvolumen am Abend des Handelstags bzw. am Folgetag; Monatsdatei wird fortgeschrieben)",
  "einheit": "Kontrakte je Tag"}
meta = {"equity": dict(common, beschreibung="OCC Tagesvolumen Aktienoptionen (Equity), alle US-Optionsbörsen"),
        "index_sonstige": dict(common, beschreibung="OCC Tagesvolumen Index- und sonstige Optionen (Index/Others)")}
json.dump(meta, open(os.path.join(OUT, "meta.json"), "w"), indent=1, ensure_ascii=False)
print(len(days), days[0], days[-1])
