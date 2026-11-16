#!/usr/bin/env python3
"""OFAC (US Treasury): «Recent Actions» je Bekanntgabetag.

Quelle: https://ofac.treasury.gov/recent-actions (HTML-Liste, 10 Meldungen je Seite,
Datum der Bekanntgabe auf der OFAC-Seite, ab Januar 2001).
Reihen:
  gesamt         Anzahl Recent-Actions-Meldungen je Kalendertag (alle Kategorien)
  listen_updates Anzahl Meldungen mit Kategorie «Sanctions List Updates»
                 (Aufnahmen/Streichungen SDN und weitere Listen)
  vollzug        Anzahl Meldungen mit Kategorie «Enforcement Actions»
                 (Vergleiche/Bussen gegen Firmen wegen Sanktionsverstoessen)
0 an Tagen ohne Meldung; Reihe endet am Vortag (UTC), damit kein angebrochener Tag
abgelegt wird.
Etappenweise: cache.json (Meldungs-URL -> [datum, kategorien]) und Fortschritt
(naechste Seite). Neue Meldungen schieben die Liste nach hinten; darum wird ab der
gespeicherten Seite weitergelesen (Doppel per URL entfernt, nichts uebersprungen).
CSV erst, wenn die letzte Seite (aelteste Meldung) einmal erreicht wurde.
"""
import concurrent.futures, datetime, gzip, html, io, json, os, re, time, urllib.error, urllib.request

ID = "ofac_recent_actions"
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
B = "https://ofac.treasury.gov/recent-actions"
BUDGET = 140
D = os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "data", "neu", ID)
CACHE = os.path.join(D, "cache.json")

ROW = re.compile(r'<div class="margin-bottom-4 search-result views-row">(.*?)</div></div></div>', re.S)
LINK = re.compile(r'<a href="([^"]+)" hreflang="en">')
DATE = re.compile(r'([A-Z][a-z]+ \d{2}, \d{4}) -')
CAT = re.compile(r'<a href="/recent-actions/[a-z-]+">([^<]+)</a>')
TOTAL = re.compile(r'Displaying \d+ - \d+ of (\d+) results')


def get(page):
    url = B if page == 0 else "%s?page=%d" % (B, page)
    req = urllib.request.Request(url, headers={"User-Agent": UA})
    with urllib.request.urlopen(req, timeout=30) as r:
        return r.read().decode("utf-8", "replace")


def parse(t):
    out = []
    for blk in ROW.findall(t):
        m = LINK.search(blk)
        dm = DATE.search(blk)
        if not m or not dm:
            raise ValueError("Zeile nicht lesbar: %r" % blk[:200])
        d = datetime.datetime.strptime(dm.group(1), "%B %d, %Y").date().isoformat()
        cats = [html.unescape(c).strip() for c in CAT.findall(blk[dm.end():])]
        out.append((m.group(1), d, cats))
    tm = TOTAL.search(t)
    return out, (int(tm.group(1)) if tm else None)


def gz(path, rows):
    buf = io.BytesIO()
    with gzip.GzipFile(fileobj=buf, mode="wb", mtime=0) as g:
        g.write(("datum,wert\n" + "".join("%s,%d\n" % r for r in rows)).encode())
    tmp = path + ".tmp"
    with open(tmp, "wb") as f:
        f.write(buf.getvalue())
    os.replace(tmp, path)


def main():
    os.makedirs(D, exist_ok=True)
    st = {"items": {}, "next_page": 0, "komplett": False}
    if os.path.exists(CACHE):
        st = json.load(open(CACHE))
    items = st["items"]
    t0 = time.time()
    # 1) Kopf: neue Meldungen ab Seite 0, bis eine Seite nur Bekanntes enthaelt
    page = 0
    while time.time() - t0 < BUDGET:
        rows, total = parse(get(page))
        neu = [r for r in rows if r[0] not in items]
        for u, d, c in rows:
            items[u] = [d, c]
        page += 1
        if not rows or (st["komplett"] and not neu) or not st["komplett"]:
            break
        time.sleep(0.5)
    # 2) Etappen rueckwaerts, bis die aelteste Seite erreicht ist
    #    (Server antwortet ~10 s je Seite; je 4 Seiten gleichzeitig)
    if not st["komplett"]:
        page = max(st["next_page"], 1)
        with concurrent.futures.ThreadPoolExecutor(4) as ex:
            while time.time() - t0 < BUDGET - 35:
                seiten = list(range(page, page + 4))
                res = list(ex.map(lambda q: parse(get(q)), seiten))
                leer = False
                for rows, tot in res:
                    if tot is not None:
                        total = tot
                    if not rows:
                        leer = True
                    for u, d, c in rows:
                        items[u] = [d, c]
                page += 4
                st["next_page"] = page
                if leer or (total is not None and page * 10 >= total):
                    st["komplett"] = True
                    break
    st["stand_utc"] = datetime.datetime.now(datetime.timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    with open(CACHE + ".tmp", "w") as f:
        json.dump(st, f, sort_keys=True, separators=(",", ":"))
    os.replace(CACHE + ".tmp", CACHE)
    print("Meldungen im Cache:", len(items), "naechste Seite:", st["next_page"], "komplett:", st["komplett"])
    if not st["komplett"]:
        return
    ges, lst, vz = {}, {}, {}
    for d, cats in items.values():
        ges[d] = ges.get(d, 0) + 1
        if "Sanctions List Updates" in cats:
            lst[d] = lst.get(d, 0) + 1
        if "Enforcement Actions" in cats:
            vz[d] = vz.get(d, 0) + 1
    start = datetime.date.fromisoformat(min(ges))
    ende = datetime.datetime.now(datetime.timezone.utc).date() - datetime.timedelta(days=1)
    tage = []
    d = start
    while d <= ende:
        tage.append(d.isoformat())
        d += datetime.timedelta(days=1)
    gz(os.path.join(D, "gesamt.csv.gz"), [(t, ges.get(t, 0)) for t in tage])
    gz(os.path.join(D, "listen_updates.csv.gz"), [(t, lst.get(t, 0)) for t in tage])
    gz(os.path.join(D, "vollzug.csv.gz"), [(t, vz.get(t, 0)) for t in tage])
    pub = ("taeglich: OFAC stellt jede Massnahme am Tag der Bekanntgabe unter Recent Actions "
           "(ofac.treasury.gov/recent-actions) mit diesem Datum ein.")
    meta = {
        "gesamt": {"einheit": "Anzahl Meldungen", "beschreibung": "OFAC Recent Actions je Bekanntgabetag, alle Kategorien (Sanktionslisten, General Licenses, Verordnungen, Leitfaeden, Sonstiges); 0 = keine Meldung", "quelle_url": B, "verdichtung": "Summe (Zaehlung je Kalendertag)", "verfuegbar_nach_tagen": 0, "publikation": pub, "revidiert": False},
        "vollzug": {"einheit": "Anzahl Meldungen", "beschreibung": "OFAC Recent Actions mit Kategorie Enforcement Actions (Vergleiche und Bussen gegen Unternehmen und Personen wegen Sanktionsverstoessen) je Bekanntgabetag; 0 = keine", "quelle_url": B, "verdichtung": "Summe (Zaehlung je Kalendertag)", "verfuegbar_nach_tagen": 0, "publikation": pub, "revidiert": False},
        "listen_updates": {"einheit": "Anzahl Meldungen", "beschreibung": "OFAC Recent Actions mit Kategorie Sanctions List Updates (Aufnahmen, Streichungen, Aenderungen SDN und weitere Listen) je Bekanntgabetag; 0 = keine", "quelle_url": B, "verdichtung": "Summe (Zaehlung je Kalendertag)", "verfuegbar_nach_tagen": 0, "publikation": pub, "revidiert": False},
    }
    with open(os.path.join(D, "meta.json"), "w") as f:
        json.dump(meta, f, ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
