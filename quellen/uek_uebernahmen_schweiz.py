#!/usr/bin/env python3
"""Schweizer Uebernahmekommission (UEK, takeover.ch): Transaktionen je Tag.

Reihen:
  angebote     Anzahl neu publizierter oeffentlicher Kaufangebote (freiwillige
               Angebote und Pflichtangebote) je Kalendertag
  rueckkaeufe  Anzahl neu publizierter Rueckkaufprogramme (Rueckkauf eigener
               Beteiligungspapiere, von der UEK freigestellt) je Kalendertag

Datum = fruehestes Dokumentdatum der Transaktion auf takeover.ch (Voranmeldung,
Angebotsprospekt, Inserat, Verfuegung usw.), d.h. der Tag der ersten
oeffentlichen Bekanntgabe auf der UEK-Seite. 0 an Tagen ohne Ereignis.

Etappen: Jede Transaktion braucht eine Detailseite (rund 930 Seiten, je ~1 s).
Der Zwischenstand liegt in data/neu/<id>/_cache_transaktionen.json. Pro Lauf
werden fehlende Detailseiten bis zu einem Zeitbudget geholt; die CSV-Dateien
werden erst geschrieben, wenn alle Transaktionen im Zwischenstand sind
(sonst Fehler, alte Dateien bleiben stehen). Transaktionen der letzten zwei
Jahre werden bei jedem Lauf neu geholt.
"""
import concurrent.futures
import datetime
import gzip
import html
import io
import json
import os
import re
import sys
import time
import urllib.error
import urllib.request

ID = "uek_uebernahmen_schweiz"
BASE = "https://www.takeover.ch"
LIST_URL = BASE + "/transactions/all/language/de"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
CACHE = os.path.join(OUT_DIR, "_cache_transaktionen.json")
BUDGET_S = 140
WORKERS = 3


def fetch(url, tries=3):
    last = None
    for i in range(tries):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            last = e
        except Exception as e:  # noqa
            last = e
        time.sleep(2 * (i + 1))
    raise last


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


def parse_list(h):
    out = {}
    for a in re.findall(r'<article class="transaction list-item".*?</article>', h, re.S):
        m = re.search(r'/transactions/detail/nr/(\d+)"', a)
        if not m:
            continue
        nr = m.group(1)
        y = re.search(r"<span>\((\d{4})\)</span>", a)
        tt = re.search(r'data-tooltip="Transaktionseigenschaft:([^"]*)"', a)
        props = html.unescape(tt.group(1)) if tt else ""
        if "Rückkaufprogramm" in props:
            kat = "rueckkaeufe"
        elif "Freiwillige Angebote" in props or "Pflichtangebote" in props:
            kat = "angebote"
        else:
            kat = "andere"
        out[nr] = {"jahr": int(y.group(1)) if y else None, "kategorie": kat}
    return out


def first_date(h, jahr, today):
    i = h.find("<main>")
    body = h[i:] if i >= 0 else h
    ds = []
    for d, m, y in re.findall(r"(?<!\d)(\d{2})\.(\d{2})\.(\d{4})(?!\d)", body):
        try:
            dt = datetime.date(int(y), int(m), int(d))
        except ValueError:
            continue
        if dt > today:
            continue
        # Dokumente vor dem Vorjahr des Listenjahres gehoeren nicht zur
        # Transaktion (Sammelseiten mit aelteren Querverweisen).
        if jahr and dt.year < jahr - 1:
            continue
        ds.append(dt)
    return min(ds).isoformat() if ds else None


def main():
    os.makedirs(OUT_DIR, exist_ok=True)
    t0 = time.time()
    today = datetime.datetime.now(datetime.timezone.utc).date()
    lst = parse_list(fetch(LIST_URL))
    if len(lst) < 500:
        raise RuntimeError("Liste unvollstaendig: %d Transaktionen" % len(lst))
    cache = {}
    if os.path.exists(CACHE):
        with open(CACHE, encoding="utf-8") as f:
            cache = json.load(f)
    todo = []
    for nr, info in sorted(lst.items(), key=lambda x: -int(x[0])):
        c = cache.get(nr)
        recent = info["jahr"] and info["jahr"] >= today.year - 1
        if c is None or recent or c.get("jahr") != info["jahr"]:
            todo.append(nr)

    def work(nr):
        if time.time() - t0 > BUDGET_S:
            return nr, None
        h = fetch(BASE + "/transactions/detail/nr/" + nr + "/language/de")
        return nr, first_date(h, lst[nr]["jahr"], today)

    done = 0
    errs = []
    with concurrent.futures.ThreadPoolExecutor(WORKERS) as ex:
        for fut in concurrent.futures.as_completed([ex.submit(work, n) for n in todo]):
            try:
                nr, d = fut.result()
            except Exception as e:  # noqa
                errs.append(str(e))
                continue
            if d is None and time.time() - t0 > BUDGET_S:
                continue
            cache[nr] = dict(lst[nr], datum=d, abruf_utc=datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"))
            done += 1
    with open(CACHE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False, sort_keys=True, indent=0)
    fehlend = [n for n in lst if n not in cache]
    print("Detailseiten geholt: %d, fehlend: %d, Fehler: %d" % (done, len(fehlend), len(errs)))
    if errs and any("403" in e or "429" in e for e in errs):
        raise RuntimeError("Sperre: " + errs[0])
    if fehlend:
        raise RuntimeError("Etappe: %d von %d Transaktionen noch nicht geholt" % (len(fehlend), len(lst)))

    counts = {"angebote": {}, "rueckkaeufe": {}}
    ohne = 0
    for nr, c in cache.items():
        if nr not in lst or c["kategorie"] not in counts:
            continue
        if not c.get("datum"):
            ohne += 1
            continue
        counts[c["kategorie"]][c["datum"]] = counts[c["kategorie"]].get(c["datum"], 0) + 1
    print("Transaktionen ohne Datum: %d" % ohne)
    alle = [d for k in counts.values() for d in k]
    start = datetime.date.fromisoformat(min(alle))
    for reihe, cnt in counts.items():
        rows = []
        d = start
        while d <= today:
            rows.append((d.isoformat(), cnt.get(d.isoformat(), 0)))
            d += datetime.timedelta(days=1)
        gzip_write(os.path.join(OUT_DIR, reihe + ".csv.gz"), rows)
        print(reihe, len(rows), sum(cnt.values()))

    gemeinsam = {
        "einheit": "Anzahl Transaktionen",
        "quelle_url": BASE + "/transactions/all",
        "verdichtung": "Anzahl Transaktionen je Kalendertag (Datum = fruehestes Dokumentdatum der Transaktion auf takeover.ch), 0 an Tagen ohne Ereignis",
        "verfuegbar_nach_tagen": 1,
        "revidiert": False,
        "publikation": "taeglich: Voranmeldungen, Angebotsprospekte und Rueckkaufinserate muessen nach UEV (SR 954.195.1, Art. 5-8 und 18) am Tag der Veroeffentlichung auch der UEK zugestellt werden, die sie auf takeover.ch mit diesem Datum aufschaltet; konservativ 1 Tag",
    }
    meta = {
        "angebote": dict(gemeinsam, beschreibung="UEK Schweiz: Anzahl neu bekanntgegebener oeffentlicher Kaufangebote (freiwillige Angebote und Pflichtangebote) fuer an der SIX kotierte Gesellschaften je Tag"),
        "rueckkaeufe": dict(gemeinsam, beschreibung="UEK Schweiz: Anzahl neu bekanntgegebener Rueckkaufprogramme eigener Beteiligungspapiere (von der UEK freigestellt) je Tag"),
    }
    with open(os.path.join(OUT_DIR, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    try:
        main()
    except Exception as e:  # noqa
        print("FEHLER:", e, file=sys.stderr)
        sys.exit(1)
