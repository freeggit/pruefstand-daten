#!/usr/bin/env python3
"""RBI: Tage mit geldpolitischer Erklaerung (Policy Statement / MPC-Resolution) laut rbi.org.in Monetary Policy Statements, ab 1998."""
import datetime, gzip, html, io, json, os, re, time, urllib.parse, urllib.request

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ROOT, "data", "neu", "indien_rbi_repo_entscheide")
UA = "pruefstand-daten/1.2 (public research mirror; github.com/freeggit/pruefstand-daten)"
URL = "https://www.rbi.org.in/Scripts/Annualpolicy.aspx"
MON = {m: i + 1 for i, m in enumerate("Jan Feb Mar Apr May Jun Jul Aug Sep Oct Nov Dec".split())}
DATUM = re.compile(r"^(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec) (\d{2}), (\d{4})$")
# Primaerdokument der Entscheidung am Tag der Bekanntgabe (keine Transkripte, Protokolle, Makro-Berichte)
PRIMAER = re.compile(r"RBI Governor announces|Statement by .{0,60}Governor|Governor.s Statement|Statement by Governor|"
                     r"Governor.s Press Statement|Resolution of the Monetary Policy Committee|^Full Statement$", re.I)
KOPF = re.compile(r"^Mid[- ]Quarter (?:Monetary Policy )?Review", re.I)


def req(data=None):
    h = {"User-Agent": UA}
    if data:
        h["Content-Type"] = "application/x-www-form-urlencoded"
    r = urllib.request.Request(URL, data=data, headers=h)
    with urllib.request.urlopen(r, timeout=30) as f:
        return f.read().decode("utf-8", "ignore")


def teile(page):
    t = re.sub(r"(?s)<script.*?</script>|<style.*?</style>", " ", page)
    t = re.sub(r"<[^>]+>", "|", t)
    t = html.unescape(re.sub(r"\s+", " ", t))
    t = t.replace("’", "'")
    i = t.find("Monetary Policy Statements|")
    j = t.find("|2026-2027|", i) if i >= 0 else -1
    if i < 0:
        return []
    t = t[i:j if j > 0 else None]
    return [x.strip() for x in t.split("|") if x.strip()]


def tage(page):
    out = set()
    kopf = {}
    akt = None
    for x in teile(page):
        m = DATUM.match(x)
        if m:
            akt = datetime.date(int(m.group(3)), MON[m.group(1)], int(m.group(2)))
            continue
        if not akt or re.search(r"Transcript|Minutes|Audio|Macroeconomic", x, re.I):
            continue
        if KOPF.search(x):
            # Ueberschrift wiederholt sich an Folgetagen (Transkripte): nur fruehester Tag je Ueberschrift
            kopf.setdefault(x, set()).add(akt)
        elif PRIMAER.search(x):
            out.add(akt)
    for ds in kopf.values():
        for d in ds:
            if not any(0 < (d - e).days <= 7 for e in ds):
                out.add(d)
    return out


def main():
    start = req()
    f = {}
    for n in ("__VIEWSTATE", "__VIEWSTATEGENERATOR", "__EVENTVALIDATION"):
        m = re.search(r'name="%s"[^>]*value="([^"]*)"' % n, start)
        f[n] = html.unescape(m.group(1)) if m else ""
    alle = set(tage(start))
    heute = datetime.datetime.now(datetime.timezone.utc).date()
    jahre = ["1999"] + [str(y) for y in range(2000, heute.year + 2)]
    for y in jahre:
        d = dict(f, hdnYear=y)
        d["UsrFontCntr$btn"] = ""
        alle |= tage(req(urllib.parse.urlencode(d).encode()))
        time.sleep(0.5)
    alle = {d for d in alle if d <= heute}
    if len(alle) < 100:
        raise SystemExit("zu wenige Termine: %d" % len(alle))
    erste = min(alle)
    os.makedirs(OUT, exist_ok=True)
    buf = io.StringIO()
    buf.write("datum,wert\n")
    d = erste
    while d <= heute:
        buf.write("%s,%d\n" % (d.isoformat(), 1 if d in alle else 0))
        d += datetime.timedelta(days=1)
    with open(os.path.join(OUT, "erklaerung.csv.gz"), "wb") as fh:
        with gzip.GzipFile(fileobj=fh, mode="wb", mtime=0, filename="") as g:
            g.write(buf.getvalue().encode())
    with open(os.path.join(OUT, "termine.json"), "w") as fh:
        json.dump(sorted(x.isoformat() for x in alle), fh, indent=0)
    meta = {"erklaerung": {
        "einheit": "0/1 (1 = Tag der Bekanntgabe einer geldpolitischen Erklaerung der RBI)",
        "beschreibung": "Reserve Bank of India: Tage, an denen eine geldpolitische Erklaerung veroeffentlicht wurde (Annual/Mid-Term/Quarterly Review, Mid-Quarter Review, Bi-monthly Policy Statement, MPC-Resolution seit Okt. 2016, sowie auf der Seite gelistete ausserordentliche Gouverneurs-Erklaerungen), laut Seite Monetary Policy Statements auf rbi.org.in. Gezaehlt wird nur der Tag mit dem Primaerdokument (Governor-Statement, Resolution, Full Statement), nicht spaetere Transkripte, Protokolle oder Makro-Vorberichte. 0 an allen anderen Tagen. Ausserordentliche Zinsschritte ohne Eintrag auf der Seite (z.B. Okt.-Dez. 2008) fehlen.",
        "quelle_url": URL,
        "verdichtung": "keine (Ereignisreihe, eine Zeile je Kalendertag)",
        "verfuegbar_nach_tagen": 0,
        "revidiert": False,
        "publikation": "taeglich (Erklaerung wird am Entscheidtag auf rbi.org.in publiziert, Quelle: RBI Monetary Policy Statements; Termine der regulaeren Sitzungen werden seit 2016 im Voraus als Meeting Schedule veroeffentlicht)",
        "status": "aktiv"}}
    with open(os.path.join(OUT, "meta.json"), "w") as fh:
        json.dump(meta, fh, indent=2, ensure_ascii=False, sort_keys=True)
    print("Termine", len(alle), "ab", erste)


if __name__ == "__main__":
    main()
