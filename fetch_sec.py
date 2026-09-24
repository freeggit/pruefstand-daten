#!/usr/bin/env python3
"""Prüfstand-Datenspiegel, Schicht «SEC»: Insiderkäufe und -verkäufe je Sektor aus Formular 4.

Quelle: SEC «Insider Transactions Data Sets» (vierteljährliche ZIP-Dateien, öffentlich, gratis).
Regeln der SEC: höchstens 10 Abrufe pro Sekunde, User-Agent mit Kontaktangabe. Bei 403: Befund, kein Umweg.

Ablauf je Lauf (in Etappen, Zeitbudget SEC_BUDGET_MIN):
 1. Fehlende Quartale holen und je Quartal zu Tageswerten je Emittent (CIK) verdichten:
    data/sec/zwischen/<JJJJqN>.csv.gz  (datum,cik,kaeufer,kaufwert,verkaeufer,verkaufwert)
    Datum = EINREICHUNGSDATUM bei der SEC; nur Formular 4 (keine Änderungen 4/A), nur nicht-derivative
    Transaktionen, Kauf = Code P mit Zugang A, Verkauf = Code S mit Abgang D. Wert = Stückzahl × Preis in USD.
 2. SIC-Code je Emittent nachschlagen (data.sec.gov/submissions), Zwischenspeicher data/sec/sic_cache.json.
 3. Je Sektor (SPDR-Sektor-ETF) und Gesamtmarkt Tagesreihen schreiben, Vertrag «datum,wert»:
    data/sec/insider/<sektor>_<groesse>.csv.gz, Manifest data/sec/manifest_sec.json.
    Status «aktiv» erst, wenn alle Quartale verarbeitet sind und mindestens 95% der Kaufwerte einem Sektor
    zugeordnet werden konnten; vorher «aufbau» (die Suchmaschine liest nur «aktiv»).
Nichts schätzen, nichts auffüllen: Tage ohne Einreichungen fehlen; Tage mit Einreichungen, aber ohne Kauf, sind 0.
"""
import csv, gzip, io, json, os, re, sys, time, zipfile, zlib, urllib.request, urllib.error
from datetime import datetime, timezone, date

UA = {"User-Agent": "pruefstand-daten freeggit@users.noreply.github.com",   # Muster der SEC: Name + Kontakt
      "Accept-Encoding": "gzip, deflate"}                                   # wie in den Beispiel-Headern der SEC
PFADE = ["structureddata", "datastandardsinnovation"]                        # die SEC nutzt seit 2026q2 auch den zweiten Pfad
OUT = "data/sec"
START = time.time()
BUDGET_MIN = float(os.environ.get("SEC_BUDGET_MIN", "15"))
ERSTES_QUARTAL = (2006, 1)
PAUSE = 0.15                                  # <= 10 Abrufe pro Sekunde
man = {"erzeugt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "reihen": {}, "hinweise": []}

def log(msg):
    print(f"[{(time.time() - START) / 60:5.1f} min] {msg}", flush=True)

def zeit_um():
    return (time.time() - START) / 60 > BUDGET_MIN

class Gesperrt(Exception):
    pass

def get(url, tries=2):
    last = None
    for i in range(tries):
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                daten, enc = r.read(), (r.headers.get("Content-Encoding") or "").lower()
                if enc == "gzip":
                    daten = gzip.decompress(daten)
                elif enc == "deflate":
                    daten = zlib.decompress(daten, -zlib.MAX_WBITS) if daten[:1] != b"x" else zlib.decompress(daten)
                return daten
        except urllib.error.HTTPError as e:
            if e.code == 403:
                try:
                    b = e.read()
                    if b[:2] == b"\x1f\x8b":
                        b = gzip.decompress(b)
                    txt = b[:3000].decode("utf-8", "replace")
                except Exception:
                    txt = ""
                txt = " ".join(re.sub(r"<[^>]+>", " ", txt).split())[:240]
                raise Gesperrt(f"{url} | Antwort SEC: {txt}")
            if e.code == 404:
                raise
            last = e; time.sleep(5 * (i + 1))
        except Exception as e:  # noqa
            last = e; time.sleep(5 * (i + 1))
    raise last

# ---------------------------------------------------------------- Sektor-Zuordnung (SIC -> SPDR-Sektor, Näherung)
def sektor(sic):
    try:
        s = int(sic)
    except Exception:
        return None
    if s == 6770: return None                                    # Mantelgesellschaften (SPAC) ausgeschlossen
    if 1300 <= s <= 1399 or 2900 <= s <= 2999: return "xle"
    if 1000 <= s <= 1499 or 2400 <= s <= 2499 or 2600 <= s <= 2699: return "xlb"
    if 2800 <= s <= 2829 or 2850 <= s <= 2899 or 3000 <= s <= 3099 or 3200 <= s <= 3399: return "xlb"
    if 2830 <= s <= 2839 or 3841 <= s <= 3851 or 8000 <= s <= 8099 or s == 5122: return "xlv"
    if 2000 <= s <= 2199 or 2840 <= s <= 2844 or 5140 <= s <= 5149 or 5400 <= s <= 5499 or s == 5912: return "xlp"
    if 3570 <= s <= 3579 or 3660 <= s <= 3679 or 7370 <= s <= 7379 or 3820 <= s <= 3829: return "xlk"
    if 2700 <= s <= 2799 or 4800 <= s <= 4899 or 7310 <= s <= 7319 or 7800 <= s <= 7899: return "xlc"
    if 4900 <= s <= 4949 or 4960 <= s <= 4991: return "xlu"
    if 6500 <= s <= 6553 or s == 6798: return "xlre"
    if 6000 <= s <= 6799: return "xlf"
    if s in (3630, 3651, 3711, 3714) or 2200 <= s <= 2399 or 2500 <= s <= 2599 or 3100 <= s <= 3199: return "xly"
    if 3860 <= s <= 3999 or 5200 <= s <= 5999 or 7000 <= s <= 7099 or 7200 <= s <= 7299 or 7900 <= s <= 8299: return "xly"
    if 1500 <= s <= 1799 or 3400 <= s <= 3569 or 3580 <= s <= 3659 or 3680 <= s <= 3819 or 3830 <= s <= 3840: return "xli"
    if 4000 <= s <= 4799 or 4950 <= s <= 4959 or 5000 <= s <= 5199 or 7300 <= s <= 7399 or 8700 <= s <= 8799: return "xli"
    return None

# ---------------------------------------------------------------- Hilfen
def quartale():
    heute = datetime.now(timezone.utc).date()
    y, q = ERSTES_QUARTAL
    while (y, q) < (heute.year, (heute.month - 1) // 3 + 1):     # laufendes Quartal ist noch nicht publiziert
        yield y, q
        y, q = (y + 1, 1) if q == 4 else (y, q + 1)

def datum(txt):
    txt = (txt or "").strip()
    for f in ("%d-%b-%Y", "%Y-%m-%d", "%m/%d/%Y", "%Y%m%d"):
        try:
            return datetime.strptime(txt.title() if "%b" in f else txt, f).date().isoformat()
        except ValueError:
            pass
    return None

def zahl(txt):
    try:
        return float((txt or "").replace(",", ""))
    except ValueError:
        return None

def tsv(zf, name):
    kand = [n for n in zf.namelist() if n.upper().endswith(name.upper() + ".TSV")]
    if not kand:
        raise RuntimeError(f"{name}.tsv fehlt im ZIP")
    with zf.open(kand[0]) as f:
        r = csv.reader(io.TextIOWrapper(f, encoding="utf-8", errors="replace"), delimiter="\t")
        kopf = [h.strip().upper() for h in next(r)]
        for zeile in r:
            yield dict(zip(kopf, zeile))

def schreibe(path, head, rows):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    buf = io.StringIO(); w = csv.writer(buf); w.writerow(head); w.writerows(rows)
    with open(path, "wb") as f:
        with gzip.GzipFile(fileobj=f, mode="wb", mtime=0, compresslevel=9) as g:
            g.write(buf.getvalue().encode("utf-8"))

def lies(path):
    with gzip.open(path, "rt", encoding="utf-8") as f:
        return list(csv.DictReader(f))

# ---------------------------------------------------------------- 1. Quartale verdichten
def quartal_verarbeiten(y, q):
    ziel = f"{OUT}/zwischen/{y}q{q}.csv.gz"
    if os.path.exists(ziel):
        return "vorhanden"
    raw, gesperrt, fehlt = None, None, 0
    for pfad in PFADE:
        url = f"https://www.sec.gov/files/{pfad}/data/insider-transactions-data-sets/{y}q{q}_form345.zip"
        try:
            raw = get(url); break
        except Gesperrt as e:
            gesperrt = e                       # kann auch «Datei nicht an diesem Pfad» heissen: zweiten Pfad versuchen
        except urllib.error.HTTPError as e:
            if e.code != 404:
                raise
            fehlt += 1
    if raw is None:
        if gesperrt is not None:
            raise gesperrt
        return "nicht publiziert"
    zf = zipfile.ZipFile(io.BytesIO(raw))
    sub = {}
    for r in tsv(zf, "SUBMISSION"):
        if (r.get("DOCUMENT_TYPE") or "").strip() != "4":
            continue
        d = datum(r.get("FILING_DATE"))
        cik = (r.get("ISSUERCIK") or "").strip().lstrip("0")
        if d and cik:
            sub[r["ACCESSION_NUMBER"]] = (d, cik)
    eigner = {}
    for r in tsv(zf, "REPORTINGOWNER"):
        eigner.setdefault(r["ACCESSION_NUMBER"], set()).add((r.get("RPTOWNERCIK") or "").strip())
    agg = {}   # (datum, cik) -> [kaeufer-set, kaufwert, verkaeufer-set, verkaufwert]
    for r in tsv(zf, "NONDERIV_TRANS"):
        acc = r.get("ACCESSION_NUMBER")
        if acc not in sub:
            continue
        code = (r.get("TRANS_CODE") or "").strip().upper()
        ad = (r.get("TRANS_ACQUIRED_DISP_CD") or "").strip().upper()
        wert = (zahl(r.get("TRANS_SHARES")) or 0) * (zahl(r.get("TRANS_PRICEPERSHARE")) or 0)
        a = agg.setdefault(sub[acc], [set(), 0.0, set(), 0.0])
        wer = {(acc, o) for o in eigner.get(acc, {"?"})}
        if code == "P" and ad == "A":
            a[0] |= wer; a[1] += wert
        elif code == "S" and ad == "D":
            a[2] |= wer; a[3] += wert
    tage = sorted({d for d, _ in sub.values()})
    rows = [[d, cik, len(v[0]), round(v[1], 2), len(v[2]), round(v[3], 2)] for (d, cik), v in sorted(agg.items())]
    # Tage mit Einreichungen, aber ohne Transaktion: als Zeile mit cik «-» festhalten (echter Nullwert)
    mit = {d for d, _ in agg}
    rows += [[d, "-", 0, 0, 0, 0] for d in tage if d not in mit]
    schreibe(ziel, ["datum", "cik", "kaeufer", "kaufwert", "verkaeufer", "verkaufwert"], sorted(rows))
    return f"{len(sub)} Formular-4-Einreichungen, {len(agg)} Emittent-Tage"

# ---------------------------------------------------------------- 2. SIC nachschlagen
def sic_nachfuehren(ciks):
    pfad = f"{OUT}/sic_cache.json"
    cache = json.load(open(pfad)) if os.path.exists(pfad) else {}
    offen = [c for c in sorted(ciks) if c not in cache and c != "-"]
    n = 0
    for c in offen:
        if zeit_um():
            break
        try:
            j = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(c):010d}.json"))
            cache[c] = str(j.get("sic") or "")
        except Gesperrt:
            json.dump(cache, open(pfad, "w")); raise
        except urllib.error.HTTPError as e:
            cache[c] = "" if e.code == 404 else cache.get(c, None)
            if cache[c] is None:
                del cache[c]
        n += 1
        if n % 500 == 0:
            json.dump(cache, open(pfad, "w")); log(f"SIC: {n} nachgeschlagen")
    json.dump(cache, open(pfad, "w"))
    return cache, len(offen) - n

# ---------------------------------------------------------------- 3. Reihen je Sektor
def reihen_schreiben(cache, fertig):
    import collections
    summe = collections.defaultdict(lambda: [0, 0.0, 0, 0.0])
    tage = set(); wert_total = 0.0; wert_zugeordnet = 0.0
    for f in sorted(os.listdir(f"{OUT}/zwischen")):
        for r in lies(f"{OUT}/zwischen/{f}"):
            d = r["datum"]; tage.add(d)
            if r["cik"] == "-":
                continue
            s = sektor(cache.get(r["cik"], ""))
            kv = float(r["kaufwert"]); wert_total += kv
            for key in (["markt"] + ([s] if s else [])):
                a = summe[(key, d)]
                a[0] += int(r["kaeufer"]); a[1] += kv; a[2] += int(r["verkaeufer"]); a[3] += float(r["verkaufwert"])
            if s:
                wert_zugeordnet += kv
    abdeckung = wert_zugeordnet / wert_total if wert_total else 0.0
    man["abdeckung_kaufwert_mit_sektor"] = round(abdeckung, 4)
    status = "aktiv" if (fertig and abdeckung >= 0.95) else "aufbau"
    tage = sorted(tage)
    for key in ["markt", "xlb", "xlc", "xle", "xlf", "xli", "xlk", "xlp", "xlre", "xlu", "xlv", "xly"]:
        for i, groesse in enumerate(["kaeufer", "kaufwert_usd", "verkaeufer", "verkaufwert_usd"]):
            rows = [[d, summe[(key, d)][i] if (key, d) in summe else 0] for d in tage]
            if not rows:
                continue
            datei = f"{OUT}/insider/{key}_{groesse}.csv.gz"
            schreibe(datei, ["datum", "wert"], rows)
            man["reihen"][f"sec_insider:{key}_{groesse}"] = {
                "datei": datei, "erste": rows[0][0], "letzte": rows[-1][0], "zeilen": len(rows),
                "einheit": "Anzahl Insider" if "kaeufer" in groesse or groesse == "verkaeufer" else "USD",
                "beschreibung": f"Formular 4, offene Markt{'käufe' if 'kauf' in groesse else 'verkäufe'} je Einreichungstag, Sektor {key}",
                "quelle_url": "https://www.sec.gov/data-research/sec-markets-data/insider-transactions-data-sets",
                "verdichtung": "Summe je Einreichungstag", "verfuegbar_nach_tagen": 1, "revidiert": False,
                "status": status}
    return status, abdeckung

if __name__ == "__main__":
    os.makedirs(f"{OUT}/zwischen", exist_ok=True)
    fertig = True
    try:
        for y, q in quartale():
            if zeit_um():
                fertig = False; man["hinweise"].append("Zeitbudget: weitere Quartale im nächsten Lauf"); break
            res = quartal_verarbeiten(y, q)
            if res != "vorhanden":
                log(f"{y}q{q}: {res}")
            if res == "nicht publiziert":
                man["hinweise"].append(f"{y}q{q} noch nicht publiziert")
    except Gesperrt as e:
        fertig = False; man["fehler"] = f"HTTP 403 der SEC ({e}); nicht umgangen, nächster Lauf erneut"; log(man["fehler"])
    except Exception as e:
        fertig = False; man["fehler"] = str(e)[:300]; log(f"Fehler Quartale: {e}")
    try:
        ciks = set()
        for f in os.listdir(f"{OUT}/zwischen"):
            ciks |= {r["cik"] for r in lies(f"{OUT}/zwischen/{f}")}
        cache, offen = ({}, len(ciks)) if "fehler" in man and "403" in man["fehler"] else sic_nachfuehren(ciks)
        if offen:
            fertig = False; man["hinweise"].append(f"SIC: {offen} Emittenten noch offen")
        if not cache and os.path.exists(f"{OUT}/sic_cache.json"):
            cache = json.load(open(f"{OUT}/sic_cache.json"))
        if ciks:
            status, abd = reihen_schreiben(cache, fertig)
            log(f"Status {status}, Abdeckung Kaufwert mit Sektor {abd:.1%}")
    except Gesperrt as e:
        man["fehler"] = f"HTTP 403 der SEC ({e}); nicht umgangen, nächster Lauf erneut"; log(man["fehler"])
    except Exception as e:
        man["fehler"] = (man.get("fehler", "") + " | " + str(e)[:300]).strip(" |"); log(f"Fehler: {e}")
    json.dump(man, open(f"{OUT}/manifest_sec.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
