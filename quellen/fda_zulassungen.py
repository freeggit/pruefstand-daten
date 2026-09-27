#!/usr/bin/env python3
import datetime
import gzip
import io
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request

ID = "fda_zulassungen"
BASE = "https://api.fda.gov/drug/drugsfda.json"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
# openFDA erlaubt keine tiefe Paginierung ueber skip ~25000 hinaus; die Abfrage
# (submission_type ORIG UND submission_status AP) liegt mit rund 25000 Treffern
# knapp darunter und deckt den gesamten Datenbestand in einem Durchgang ab.
MAX_SKIP = 25000
PAGE = 1000


def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except urllib.error.HTTPError as e:
            if e.code == 404:
                return {"results": [], "meta": {"results": {"total": 0}}}
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(2 * (i + 1))


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
    q = "submissions.submission_type:ORIG AND submissions.submission_status:AP"
    approvals = {}  # application_number -> datum (aelteste ORIG-AP-Zulassung)
    last_updated = None
    skip = 0
    while skip <= MAX_SKIP:
        url = BASE + "?" + urllib.parse.urlencode(
            {"search": q, "limit": PAGE, "skip": skip}
        )
        d = fetch(url)
        last_updated = d.get("meta", {}).get("last_updated", last_updated)
        results = d.get("results", [])
        if not results:
            break
        for rec in results:
            app_num = rec.get("application_number", "")
            # Nur neue Wirkstoffe/Biologika (NDA, BLA), keine Generika (ANDA)
            if not (app_num.startswith("NDA") or app_num.startswith("BLA")):
                continue
            for s in rec.get("submissions", []):
                if s.get("submission_type") == "ORIG" and s.get("submission_status") == "AP":
                    dt = s.get("submission_status_date")
                    if not dt or len(dt) != 8:
                        continue
                    iso = "%s-%s-%s" % (dt[0:4], dt[4:6], dt[6:8])
                    try:
                        datetime.date.fromisoformat(iso)
                    except ValueError:
                        continue
                    prev = approvals.get(app_num)
                    if prev is None or iso < prev:
                        approvals[app_num] = iso
        skip += PAGE
        if len(results) < PAGE:
            break

    if not approvals:
        raise RuntimeError("keine Zulassungen gefunden")

    counts = {}
    for iso in approvals.values():
        counts[iso] = counts.get(iso, 0) + 1

    first_day = min(datetime.date.fromisoformat(d) for d in counts)
    # bis zum von der API gemeldeten Aktualisierungsstand zero-fillen (nicht nur bis
    # zum letzten Ereignis), sonst waere K5 nicht pruefbar: Tage ohne Zulassung nach
    # dem letzten Treffer sind echte Nullen, keine fehlenden Daten.
    today = datetime.datetime.now(datetime.timezone.utc).date()
    if last_updated:
        try:
            cutoff = datetime.date.fromisoformat(last_updated)
        except ValueError:
            cutoff = max(datetime.date.fromisoformat(d) for d in counts)
    else:
        cutoff = max(datetime.date.fromisoformat(d) for d in counts)
    last_day = min(cutoff, today)
    last_day = max(last_day, max(datetime.date.fromisoformat(d) for d in counts))
    rows = []
    d = first_day
    while d <= last_day:
        iso = d.isoformat()
        rows.append((iso, counts.get(iso, 0)))
        d += datetime.timedelta(days=1)

    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "zulassungen.csv.gz"), rows)

    meta = {
        "zulassungen": {
            "einheit": "Anzahl Zulassungen",
            "beschreibung": (
                "Taegliche Anzahl neu zugelassener Wirkstoffe und Biologika in den USA "
                "(FDA-Erstzulassungen, ORIG-Submissions mit Status AP, nur NDA/BLA, "
                "keine Generika-ANDA), Datum = FDA-Entscheiddatum (submission_status_date)"
            ),
            "quelle_url": BASE,
            "verdichtung": "Summe der Erstzulassungen je Kalendertag (submission_status_date)",
            "publikation": "taeglich, mit kurzer Verzoegerung durch den Aktualisierungszyklus von openFDA drugsfda (siehe Feld meta.last_updated der API-Antwort, beobachtet ca. 3-10 Tage)",
            "verfuegbar_nach_tagen": 10,
            "revidiert": False,
        }
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
