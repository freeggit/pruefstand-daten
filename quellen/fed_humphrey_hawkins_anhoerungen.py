#!/usr/bin/env python3
"""Federal Reserve: Tage der halbjaehrlichen geldpolitischen Anhoerung (Monetary Policy Report,
frueher Humphrey-Hawkins) im US-Kongress, erster Anhoerungstag je Bericht.
Quelle: https://www.federalreserve.gov/monetarypolicy/publications/mpr_default.htm (Links auf die
Testimony-Seiten ab Juli 1996). Ab 2006 steht das Datum in der URL (<name>JJJJMMTTa.htm), davor
wird es aus der Testimony-Seite gelesen (fruehestes genanntes Anhoerungsdatum, Senat oder
Repraesentantenhaus). Nur die halbjaehrlichen Berichte, keine Folgeanhoerungen (z.B. April 2003).
Reihe 0/1 fuer jeden Kalendertag ab 1996-03-01 (Februar-Anhoerung 1996 fehlt in der Quelle)."""
import datetime, gzip, io, json, os, re, time, urllib.request, html as H

ID = "fed_humphrey_hawkins_anhoerungen"
URL = "https://www.federalreserve.gov/monetarypolicy/publications/mpr_default.htm"
BASE = "https://www.federalreserve.gov"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
OUT = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
START = datetime.date(1996, 3, 1)
MONATE = {m: i + 1 for i, m in enumerate(["January", "February", "March", "April", "May", "June", "July",
                                          "August", "September", "October", "November", "December"])}


def fetch(url):
    for i in range(4):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("latin-1")
        except Exception:
            if i == 3:
                raise
            time.sleep(2 * (i + 1))


def text(h):
    return re.sub(r"\s+", " ", H.unescape(re.sub(r"<[^>]+>", " ", h)))


def write(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as gz:
        gz.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    with open(path, "wb") as f:
        f.write(buf.getvalue())


def main():
    h = fetch(URL)
    links = re.findall(r'<a[^>]*href="([^"]*)"[^>]*>\s*Testimony', h)
    tage = set()
    for l in links:
        u = l if l.startswith("http") else BASE + l
        m = re.search(r"/testimony/[a-z]+(\d{4})(\d{2})(\d{2})[a-z]?\.htm", u)
        if m:
            tage.add(datetime.date(int(m.group(1)), int(m.group(2)), int(m.group(3))))
            continue
        m = re.search(r"/boarddocs/hh/(\d{4})/([A-Za-z]+)/", u)
        if not m:
            raise RuntimeError("unbekannter Link: " + u)
        jahr = int(m.group(1))
        t = text(fetch(u))
        if "follow-up" in t[:400].lower():
            continue  # Folgeanhoerung, kein halbjaehrlicher Bericht
        i = max(t.find("Before the "), 0)
        kand = []
        for mo, d, y in re.findall(r"([A-Z][a-z]+) (\d{1,2}), (\d{4})", t[i:i + 1500]):
            if mo in MONATE and int(y) == jahr:
                kand.append(datetime.date(jahr, MONATE[mo], int(d)))
        if not kand:
            raise RuntimeError("kein Datum: " + u)
        tage.add(min(kand))
        time.sleep(0.3)
    if len(tage) < 55:
        raise RuntimeError("zu wenige Anhoerungen: %d" % len(tage))
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    rows, d = [], START
    while d <= heute:
        rows.append((d.isoformat(), 1 if d in tage else 0))
        d += datetime.timedelta(days=1)
    os.makedirs(OUT, exist_ok=True)
    write(os.path.join(OUT, "erste_anhoerung.csv.gz"), rows)
    meta = {"erste_anhoerung": {
        "einheit": "0/1",
        "beschreibung": "1 = erster Anhoerungstag des Fed-Vorsitzes zum halbjaehrlichen Monetary Policy Report im US-Kongress (Senat oder Repraesentantenhaus), sonst 0; ab 1996-03-01",
        "quelle_url": URL,
        "verdichtung": "keine (Ereignistag)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich: Testimony wird am Anhoerungstag auf federalreserve.gov veroeffentlicht; der Anhoerungstermin wird vom Kongressausschuss vorab angekuendigt",
        "status": "aktiv"}}
    with open(os.path.join(OUT, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)
    print(ID, len(tage), "Anhoerungen", min(tage), max(tage))


if __name__ == "__main__":
    main()
