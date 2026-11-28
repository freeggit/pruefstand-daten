#!/usr/bin/env python3
"""US Supreme Court: Anzahl verkuendeter Urteile je Kalendertag.

Historie: Supreme Court Database (SCDB, offizielle Projektseite scdb.wustl.edu,
Modern Database, case centered, Citation), Feld dateDecision = Tag der
Verkuendung. Verwendet fuer Tage vor 2019-10-01 (Beginn Term 2019).
Ab Term 2019: offizielle Slip-Opinion-Listen www.supremecourt.gov/opinions/slipopinion/<TT>
(Spalte Date = Verkuendungstag). Ausgeschlossen: SCDB decisionType 4 (Decrees),
in den Slip-Listen nicht enthalten: Opinions Relating to Orders.
"""
import csv
import datetime
import gzip
import io
import json
import os
import re
import time
import urllib.request
import zipfile

ID = "supreme_court_urteilstage"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
SCDB_PAGE = "http://scdb.wustl.edu/data.php"
SLIP = "https://www.supremecourt.gov/opinions/slipopinion/%02d"
SEAM = datetime.date(2019, 10, 1)


def fetch(url, tries=3):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


def gzip_write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        t = io.TextIOWrapper(gz, encoding="utf-8", newline="")
        t.write("datum,wert\n")
        for d, v in rows:
            t.write("%s,%s\n" % (d, v))
        t.flush()
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def scdb_counts():
    page = fetch(SCDB_PAGE).decode("utf-8", "replace")
    links = sorted(set(re.findall(r'_brickFiles/(\d{4}_\d{2})/SCDB_\1_caseCentered_Citation\.csv\.zip', page)))
    if not links:
        raise RuntimeError("SCDB: kein caseCentered_Citation.csv.zip gefunden")
    rel = links[-1]
    url = "http://scdb.wustl.edu/_brickFiles/%s/SCDB_%s_caseCentered_Citation.csv.zip" % (rel, rel)
    z = zipfile.ZipFile(io.BytesIO(fetch(url)))
    name = [n for n in z.namelist() if n.endswith(".csv")][0]
    counts = {}
    for row in csv.DictReader(io.TextIOWrapper(z.open(name), encoding="latin-1")):
        if row.get("decisionType") == "4":
            continue
        m, d, y = row["dateDecision"].split("/")
        dt = datetime.date(int(y), int(m), int(d))
        if dt < SEAM:
            counts[dt] = counts.get(dt, 0) + 1
    return counts, rel


def slip_counts(today):
    last_term = today.year if today.month >= 10 else today.year - 1
    counts = {}
    for term in range(2019, last_term + 1):
        html = fetch(SLIP % (term % 100)).decode("utf-8", "replace")
        ds = re.findall(r"<td[^>]*>\s*(\d{1,2}/\d{1,2}/\d{2})\s*</td>", html)
        if not ds and term < last_term:
            raise RuntimeError("Slip-Liste Term %d leer" % term)
        for s in ds:
            dt = datetime.datetime.strptime(s, "%m/%d/%y").date()
            if dt >= SEAM:
                counts[dt] = counts.get(dt, 0) + 1
    return counts


def main():
    today = datetime.datetime.now(datetime.timezone.utc).date()
    a, rel = scdb_counts()
    b = slip_counts(today)
    counts = dict(a)
    for k, v in b.items():
        counts[k] = counts.get(k, 0) + v
    first = min(counts)
    rows = []
    cur = first
    while cur <= today:
        rows.append((cur.isoformat(), counts.get(cur, 0)))
        cur += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "anzahl_urteile.csv.gz"), rows)
    meta = {
        "anzahl_urteile": {
            "einheit": "Anzahl Urteile",
            "beschreibung": (
                "Anzahl am Tag verkuendeter Urteile des US Supreme Court, 0 an Tagen ohne Verkuendung. "
                "Bis 30.9.2019 aus der Supreme Court Database (Release %s, case centered, Citation, "
                "dateDecision, ohne decisionType 4 Decrees), ab Term 2019 aus den offiziellen "
                "Slip-Opinion-Listen von supremecourt.gov (Opinions of the Court inkl. Per Curiam)." % rel
            ),
            "quelle_url": "https://www.supremecourt.gov/opinions/slipopinion/%02d" % (today.year % 100),
            "verdichtung": "Anzahl Urteile je Kalendertag (Verkuendungstag)",
            "publikation": (
                "taeglich: Urteile werden an der Sitzung verkuendet und gleichentags um ca. 10 Uhr ET "
                "auf supremecourt.gov als Slip Opinion veroeffentlicht (Seite Opinions of the Court)"
            ),
            "verfuegbar_nach_tagen": 0,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
