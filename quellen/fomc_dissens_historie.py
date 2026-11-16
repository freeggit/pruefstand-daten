#!/usr/bin/env python3
"""FOMC-Gegenstimmen je Statement-Tag (federalreserve.gov), ab dem ersten Statement mit Stimmenliste (2002)."""
import datetime, gzip, json, os, re, time, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "neu", "fomc_dissens_historie")
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
BASE = "https://www.federalreserve.gov"


def get(url):
    for i in range(3):
        try:
            req = urllib.request.Request(url, headers={"User-Agent": UA})
            with urllib.request.urlopen(req, timeout=30) as r:
                return r.read().decode("utf-8", "replace")
        except urllib.error.HTTPError as e:
            if e.code in (403, 429):
                raise
            if i == 2:
                raise
        except Exception:
            if i == 2:
                raise
        time.sleep(2)


def text(html):
    html = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", html)
    t = re.sub(r"<[^>]+>", " ", html)
    t = t.replace("&#160;", " ").replace("&nbsp;", " ").replace("&amp;", "&")
    return re.sub(r"\s+", " ", t)


LINK = re.compile(r'href="(/(?:newsevents/press(?:releases)?/monetary/?|boarddocs/press/(?:monetary|general)/\d{4}/)(\d{8})[a-z]?(?:\.htm|/default\.htm|/)?)"[^>]*>\s*Statement\s*<')
AGAINST = re.compile(r"Voting against(?: (?:the|this|these) [^.;]{0,40}?actions?)? (?:was|were):? ")
# STOP alt
_STOP = re.compile(r",? who |,? each of whom|\s+(?:President|Governor|Presidents|Governors) [A-Z]|\.\s+(?:Mr|Ms|Mrs|In |Absent|Implementation|For |The |Last |\d)|\.\s*$")
FOR = re.compile(r"Voting (?:\(by notation\) )?for ")
# Format ab Juni 2026: "approved the following statement for release by a 12 - 0 vote"
TALLY = re.compile(r"by an? (\d{1,2})\s*[\u2013\u2014-]\s*(\d{1,2}) vote")


def auszug(t):
    i = [m.start() for m in (FOR.search(t), TALLY.search(t)) if m]
    if not i:
        return None
    i = min(i)
    return t[max(0, i - 200): i + 2500]


def zaehle(t):
    m = TALLY.search(t)
    if m and not FOR.search(t):
        return int(m.group(2)), [m.group(0)]
    n = 0
    segs = []
    for m in AGAINST.finditer(t):
        rest = t[m.end():m.end() + 900]
        rest = re.sub(r",? Jr\.", " Jr", rest)
        # Satzende: Folgesatz ueber Governor/President, Absent, Implementation usw.
        e = re.search(r"\.\s+(?:Governors?|Presidents?|Mr|Ms|Mrs|Messrs|In |Absent|Implementation|For |The |Last |\d)|\.\s*$", rest)
        seg = rest[: e.start()] if e else rest[:400]
        # Begruendungen ("who preferred ...", "each of whom ...") bis zum naechsten Namen entfernen
        seg = re.sub(r",?\s*(?:each of )?(?:who|whom)\b.*?(?=,? and [A-Z][a-z]+ [A-Z]|;|$)", "", seg)
        namen = [x.strip() for x in re.split(r";|,| and ", seg) if x.strip()]
        namen = [x for x in namen if re.match(r"^[A-Z][a-z]+(?: [A-Z]\.)*(?: [A-Z][A-Za-z']+)+(?: Jr)?\.?$", x)]
        n += len(namen)
        segs.append(seg)
    return n, segs


def main():
    links = {}
    heute = datetime.date.today()
    for y in range(2002, heute.year + 1):
        url = BASE + ("/monetarypolicy/fomchistorical%d.htm" % y)
        try:
            h = get(url)
        except urllib.error.HTTPError as e:
            if e.code == 404:
                continue
            raise
        for m in LINK.finditer(h):
            links.setdefault(m.group(2), set()).add(m.group(1))
    h = get(BASE + "/monetarypolicy/fomccalendars.htm")
    for m in re.finditer(r'href="(/newsevents/pressreleases/monetary(\d{8})[a-z]\.htm)"', h):
        if m.group(1).endswith("a.htm"):
            links.setdefault(m.group(2), set()).add(m.group(1))
    # Zwischenspeicher: Statements aendern sich nach Veroeffentlichung nicht
    cache_p = os.path.join(OUT, "statements.json")
    cache = {}
    if os.path.exists(cache_p):
        for x in json.load(open(cache_p, encoding="utf-8")):
            cache[x["url"]] = x
    ereignisse = {}
    protokoll = []
    for d in sorted(links):
        if d < "20020101":
            continue
        dt = datetime.date(int(d[:4]), int(d[4:6]), int(d[6:]))
        for u in sorted(links[d]):
            if u in cache and "auszug" in cache[u]:
                a = cache[u]["auszug"]
            else:
                a = auszug(text(get(BASE + u)))
                time.sleep(0.15)
            if a is None:
                x = {"datum": dt.isoformat(), "url": u, "auszug": None, "stimmenliste": False, "gegenstimmen": 0, "text": []}
            else:
                n, segs = zaehle(a)
                x = {"datum": dt.isoformat(), "url": u, "auszug": a, "stimmenliste": True, "gegenstimmen": n, "text": segs}
            protokoll.append(x)
            if x["stimmenliste"]:
                ereignisse[dt] = max(ereignisse.get(dt, 0), x["gegenstimmen"])
    if len(ereignisse) < 150:
        raise SystemExit("zu wenige Statements: %d" % len(ereignisse))
    start = min(ereignisse)
    ende = heute - datetime.timedelta(days=1)
    os.makedirs(OUT, exist_ok=True)
    zeilen = ["datum,wert"]
    d = start
    while d <= ende:
        zeilen.append("%s,%d" % (d.isoformat(), ereignisse.get(d, 0)))
        d += datetime.timedelta(days=1)
    raw = ("\n".join(zeilen) + "\n").encode()
    with open(os.path.join(OUT, "gegenstimmen.csv.gz"), "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, filename="") as g:
            g.write(raw)
    with open(cache_p, "w", encoding="utf-8") as f:
        json.dump(protokoll, f, ensure_ascii=False, indent=1)
    meta = {"gegenstimmen": {
        "einheit": "Anzahl Gegenstimmen (0 an Tagen ohne Statement)",
        "beschreibung": "Zahl der FOMC-Mitglieder, die laut Statement gegen den geldpolitischen Beschluss stimmten, am Tag der Veroeffentlichung des Statements (14 Uhr Washington, seit Maerz 2002 mit Namensliste der Abstimmung, ab Juni 2026 nur noch als Stimmenverhaeltnis 'by a 12 - 0 vote', dann Gegenstimmen = zweite Zahl); 0 an allen anderen Tagen, auch an Statement-Tagen ohne Gegenstimme. Alle auf federalreserve.gov gelisteten Statements, auch ausserordentliche Sitzungen (Inhalt wird am selben Tag publiziert). Begruendungstexte je Statement in statements.json.",
        "quelle_url": "https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm",
        "verdichtung": "keine (Ereignisreihe, eine Zeile je Kalendertag)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich (Stimmenliste steht im Statement, das am Entscheidtag um 14 Uhr Washingtoner Zeit veroeffentlicht wird; Quelle: federalreserve.gov Pressemitteilungen monetary<datum>a.htm)",
        "status": "aktiv",
    }}
    with open(os.path.join(OUT, "meta.json"), "w", encoding="utf-8") as f:
        json.dump(meta, f, ensure_ascii=False, indent=2, sort_keys=True)


if __name__ == "__main__":
    main()
