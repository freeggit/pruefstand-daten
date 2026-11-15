#!/usr/bin/env python3
"""Federal Reserve Board: Anzahl Reden von Board-Mitgliedern je Tag.
Quellen: https://www.federalreserve.gov/json/ne-speeches.json (ab 2006) und die Jahresseiten
https://www.federalreserve.gov/newsevents/speech/<JJJJ>speech.htm fuer 1996 bis 2005.
Datum = Tag der Rede (US-Ostzeit), Rede am selben Tag auf federalreserve.gov veroeffentlicht."""
import datetime, gzip, io, json, os, re, time, urllib.request

ID = "fed_reden_dichte"
JSON_URL = "https://www.federalreserve.gov/json/ne-speeches.json"
JAHR_URL = "https://www.federalreserve.gov/newsevents/speech/%dspeech.htm"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
MONATE = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                          "August", "September", "October", "November", "December"])}


def fetch(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read()
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    reden = set()  # (datum, sprecher, titel)
    d = json.loads(fetch(JSON_URL).decode("utf-8-sig"))
    for x in d:
        if "d" not in x:
            continue
        m, t, y = x["d"].split()[0].split("/")
        reden.add((datetime.date(int(y), int(m), int(t)), x.get("s", "").strip(), x.get("t", "").strip()))
    n_json = len(reden)
    if n_json < 1000:
        raise RuntimeError("zu wenige Reden im JSON: %d" % n_json)
    for jahr in range(1996, 2006):
        h = fetch(JAHR_URL % jahr).decode("latin-1")
        ul = h[h.find('id="speechIndex"'):]
        for li in re.findall(r"<li>(.*?)</li>", ul, re.S):
            m = re.match(r"\s*([A-Z][a-z]+) (\d{1,2}), (\d{4})", li)
            if not m or m.group(1) not in MONATE:
                continue
            dt = datetime.date(int(m.group(3)), MONATE[m.group(1)], int(m.group(2)))
            sp = re.search(r'class="speaker">\s*(.*?)\s*</div>', li, re.S)
            ti = re.search(r'class="title">.*?>(.*?)</a>', li, re.S)
            reden.add((dt, sp.group(1).strip() if sp else "", ti.group(1).strip() if ti else ""))
        time.sleep(0.3)
    alle, vorsitz = {}, {}
    for dt, sp, _ in reden:
        alle[dt] = alle.get(dt, 0) + 1
        if sp.startswith("Chair"):
            vorsitz[dt] = vorsitz.get(dt, 0) + 1
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    start = min(alle)
    os.makedirs(OUT, exist_ok=True)
    for reihe, z in (("anzahl", alle), ("vorsitz", vorsitz)):
        rows, cur = [], start
        while cur <= heute:
            rows.append((cur.isoformat(), z.get(cur, 0)))
            cur += datetime.timedelta(days=1)
        write(os.path.join(OUT, reihe + ".csv.gz"), rows)
    pub = ("taeglich: Reden der Board-Mitglieder werden am Tag der Rede auf federalreserve.gov/newsevents/speeches.htm "
           "veroeffentlicht und im Voraus im Wochenkalender angekuendigt (federalreserve.gov/newsevents/calendar.htm)")
    q = "https://www.federalreserve.gov/newsevents/speeches.htm"
    meta = {
        "anzahl": {
            "einheit": "Anzahl Reden",
            "beschreibung": "Taegliche Anzahl Reden von Mitgliedern des Federal Reserve Board (Vorsitz, Vize, Gouverneure), "
                            "Datum = Tag der Rede (US-Ostzeit), 0 an Tagen ohne Rede; ab Juni 1996 (Beginn des Online-Archivs), "
                            "ohne Anhoerungen (Testimony) und ohne Reden der Regionalbank-Praesidenten",
            "quelle_url": q, "verdichtung": "Anzahl Reden je Kalendertag",
            "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
        "vorsitz": {
            "einheit": "Anzahl Reden",
            "beschreibung": "Taegliche Anzahl Reden des Fed-Vorsitzenden (Sprecher beginnt mit 'Chair'), Datum = Tag der Rede, "
                            "0 an Tagen ohne Rede; ab 1996",
            "quelle_url": q, "verdichtung": "Anzahl Reden je Kalendertag",
            "verfuegbar_nach_tagen": 0, "revidiert": False, "publikation": pub},
    }
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
