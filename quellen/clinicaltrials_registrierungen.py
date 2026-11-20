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

ID = "clinicaltrials_registrierungen"
BASE = "https://clinicaltrials.gov/api/v2/studies"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(__file__), "..", "data", "neu", ID)
def fetch(url, tries=4):
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as resp:
                return json.loads(resp.read().decode("utf-8"))
        except Exception:
            if i == tries - 1:
                raise
            time.sleep(3 * (i + 1))


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
    params = {
        "filter.advanced": "AREA[StudyFirstPostDate]RANGE[2000-01-01,MAX] AND AREA[Phase]PHASE3 AND AREA[LeadSponsorClass]INDUSTRY",
        "fields": "NCTId,StudyFirstPostDate,Phase,LeadSponsorClass",
        "pageSize": 1000,
        "sort": "StudyFirstPostDate:asc",
    }
    studies = {}
    token = None
    t0 = time.time()
    while True:
        p = dict(params)
        if token:
            p["pageToken"] = token
        d = fetch(BASE + "?" + urllib.parse.urlencode(p))
        for s in d.get("studies", []):
            ps = s.get("protocolSection", {})
            nct = ps.get("identificationModule", {}).get("nctId")
            dt = ps.get("statusModule", {}).get("studyFirstPostDateStruct", {}).get("date")
            if not nct or not dt or len(dt) != 10:
                continue  # Monatsdatum ohne Tag nicht verwendbar
            phases = ps.get("designModule", {}).get("phases", []) or []
            spons = ps.get("sponsorCollaboratorsModule", {}).get("leadSponsor", {}).get("class")
            if "PHASE3" in phases and spons == "INDUSTRY":
                studies[nct] = dt
        token = d.get("nextPageToken")
        if not token:
            break
        if time.time() - t0 > 150:
            raise RuntimeError("Zeitlimit")
    if len(studies) < 1000:
        raise RuntimeError("zu wenige Studien")
    counts = {}
    for dt in studies.values():
        counts[dt] = counts.get(dt, 0) + 1
    first = min(datetime.date.fromisoformat(v) for v in studies.values())
    last = min(datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1),
               max(datetime.date.fromisoformat(v) for v in studies.values()))
    rows = []
    day = first
    while day <= last:
        rows.append((day.isoformat(), counts.get(day.isoformat(), 0)))
        day += datetime.timedelta(days=1)
    os.makedirs(OUT_DIR, exist_ok=True)
    gzip_write(os.path.join(OUT_DIR, "registrierungen_phase3_industrie.csv.gz"), rows)
    meta = {
        "registrierungen_phase3_industrie": {
            "einheit": "Anzahl Studien",
            "beschreibung": "Neu registrierte Phase-3-Studien (inkl. Phase 2/3) mit Industrie-Sponsor (leadSponsor.class INDUSTRY), die an diesem Tag erstmals auf ClinicalTrials.gov veroeffentlicht wurden (StudyFirstPostDate)",
            "quelle_url": "https://clinicaltrials.gov/data-api/api",
            "verdichtung": "Summe je Kalendertag (StudyFirstPostDate), Nullen an Tagen ohne Veroeffentlichung",
            "publikation": "taeglich: ClinicalTrials.gov stellt eine Studie am Tag StudyFirstPostDate oeffentlich (Feld studyFirstPostDateStruct der API v2, Definition 'First Posted'); Abruf am Folgetag",
            "verfuegbar_nach_tagen": 1, "revidiert": False},
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
