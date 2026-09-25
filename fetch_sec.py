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

Zugang (ab 25.9.2026): User-Agent mit echter Kontaktadresse aus dem GitHub-Secret SEC_USER_AGENT (nie im Code, nie in
Dateien). Höchstens 1 Abruf pro Sekunde für Quartalsdateien, 4 pro Sekunde für SIC-Abfragen (SEC-Grenze: 10).
Sperrstatus laufübergreifend in data/sec/zugang.json: bei 403 Zähler, Zeitpunkte, Antwort, Retry-After, öffentliche IP
des Runners. Nach 7 Tagen Sperre Status ACCESS_BLOCKED: dann höchstens ein Testabruf pro Woche (oder sofort, wenn sich
die Kontaktangabe geändert hat), bis Reto die Sperre mit webmaster@sec.gov geklärt hat. Herkunft je Quartal
(URL, Grösse, SHA-256, Abrufzeit) in data/sec/herkunft.json; einmal im Monat werden die letzten 8 Quartale auf
geänderte Dateigrösse geprüft und bei Änderung neu geholt (die SEC ergänzt publizierte Datensätze gelegentlich).
"""
import hashlib
import csv, gzip, io, json, os, re, sys, time, zipfile, zlib, urllib.request, urllib.error
from datetime import datetime, timezone, date

KONTAKT = os.environ.get("SEC_USER_AGENT", "").strip()                       # z.B. «Pruefstand Research name@domain»
UA = {"User-Agent": KONTAKT or "pruefstand-daten freeggit@users.noreply.github.com",   # Muster der SEC: Name + Kontakt
      "Accept-Encoding": "gzip, deflate"}                                   # wie in den Beispiel-Headern der SEC
KONTAKT_KENNUNG = hashlib.sha256(UA["User-Agent"].encode()).hexdigest()[:10]   # nur Kennung, nie die Adresse selbst
PFADE = ["structureddata", "datastandardsinnovation"]                        # die SEC nutzt seit 2026q2 auch den zweiten Pfad
OUT = "data/sec"
START = time.time()
BUDGET_MIN = float(os.environ.get("SEC_BUDGET_MIN", "15"))
ERSTES_QUARTAL = (2006, 1)
PAUSE = 1.0                                   # Quartalsdateien: höchstens 1 Abruf pro Sekunde
PAUSE_SIC = 0.25                              # SIC-Abfragen: höchstens 4 pro Sekunde (SEC-Grenze 10)
LETZTE = {}                                   # Kopfzeilen der letzten Antwort (Herkunft)
man = {"erzeugt_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), "reihen": {}, "hinweise": []}

def log(msg):
    print(f"[{(time.time() - START) / 60:5.1f} min] {msg}", flush=True)

def zeit_um():
    return (time.time() - START) / 60 > BUDGET_MIN

class Gesperrt(Exception):
    def __init__(self, msg, retry_after=None):
        super().__init__(msg); self.retry_after = retry_after

def get(url, tries=2, pause=None):
    last = None
    for i in range(tries):
        try:
            time.sleep(PAUSE if pause is None else pause)
            with urllib.request.urlopen(urllib.request.Request(url, headers=UA), timeout=60) as r:
                LETZTE.clear(); LETZTE.update({"content_length": r.headers.get("Content-Length"), "etag": r.headers.get("ETag"),
                                               "last_modified": r.headers.get("Last-Modified")})
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
                txt = re.sub(r"(?is)<(style|script)[^>]*>.*?</\1>", " ", txt)
                txt = " ".join(re.sub(r"<[^>]+>", " ", txt).split())[:400]
                ra = (e.headers.get("Retry-After") if e.headers else None)
                if ra and ra.strip().isdigit() and int(ra) <= 600 and i == 0:
                    log(f"403 mit Retry-After {ra} s: warte einmal"); time.sleep(int(ra) + 5); continue
                raise Gesperrt(f"{url} | Antwort SEC: {txt}", ra)
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
    try:
        zf = zipfile.ZipFile(io.BytesIO(raw))
        if zf.testzip() is not None:
            raise zipfile.BadZipFile("Prüfsumme im ZIP falsch")
    except zipfile.BadZipFile as e:
        raise RuntimeError(f"{y}q{q}: keine gültige ZIP-Datei ({e}; {len(raw)} Bytes) – nicht als Erfolg gewertet")
    HERKUNFT[f"{y}q{q}"] = {"url": url, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest(),
                            "abruf_utc": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"), **LETZTE}
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
            j = json.loads(get(f"https://data.sec.gov/submissions/CIK{int(c):010d}.json", pause=PAUSE_SIC))
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

# ---------------------------------------------------------------- Zugang, Herkunft, Revisionen
def jetzt():
    return datetime.now(timezone.utc)

def lade_json(pfad, leer):
    try:
        return json.load(open(pfad, encoding="utf-8"))
    except Exception:
        return leer

ZUG = lade_json(f"{OUT}/zugang.json", {"status": "ok"})
HERKUNFT = lade_json(f"{OUT}/herkunft.json", {})

def runner_ip():
    try:
        return urllib.request.urlopen("https://api.ipify.org", timeout=10).read().decode().strip()
    except Exception:
        return None

def sperre_melden(e):
    t = jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")
    ZUG["anzahl_403"] = int(ZUG.get("anzahl_403", 0)) + 1
    ZUG.setdefault("erster_403_utc", t)
    ZUG.update({"letzter_403_utc": t, "letzte_antwort": str(e)[:600], "retry_after": getattr(e, "retry_after", None),
                "runner_ip": runner_ip(), "kontakt_aus_secret": bool(KONTAKT), "kontakt_kennung": KONTAKT_KENNUNG})
    tage = (jetzt() - datetime.fromisoformat(ZUG["erster_403_utc"].replace("Z", "+00:00"))).days
    ZUG["status"] = "ACCESS_BLOCKED" if tage >= 7 else "gesperrt"
    if ZUG["status"] == "ACCESS_BLOCKED":
        ZUG["naechster_schritt"] = ("Reto: Mail an webmaster@sec.gov mit Fehlermeldung, öffentlicher IP (runner_ip), URL, "
                                    "Zeitpunkt und User-Agent. Bis dahin höchstens ein Testabruf pro Woche.")
    man["fehler"] = f"HTTP 403 der SEC seit {ZUG['erster_403_utc']} ({ZUG['anzahl_403']}x, Status {ZUG['status']}): {e}; nicht umgangen"
    log(man["fehler"])

def zugang_ok():
    if ZUG.get("status") != "ok":
        ZUG["letzte_sperre"] = {k: ZUG.get(k) for k in ("erster_403_utc", "letzter_403_utc", "anzahl_403")}
    for k in ("erster_403_utc", "letzter_403_utc", "anzahl_403", "letzte_antwort", "retry_after", "naechster_schritt"):
        ZUG.pop(k, None)
    ZUG.update({"status": "ok", "letzter_erfolg_utc": jetzt().strftime("%Y-%m-%dT%H:%M:%SZ"),
                "kontakt_aus_secret": bool(KONTAKT), "kontakt_kennung": KONTAKT_KENNUNG})

def darf_versuchen():
    """ACCESS_BLOCKED: nur ein Testabruf pro Woche, ausser die Kontaktangabe hat sich geändert."""
    if ZUG.get("status") != "ACCESS_BLOCKED":
        return True
    if ZUG.get("kontakt_kennung") != KONTAKT_KENNUNG:
        log("Kontaktangabe geändert: ein neuer Versuch trotz ACCESS_BLOCKED"); return True
    letzter = datetime.fromisoformat(ZUG.get("letzter_test_utc", ZUG.get("letzter_403_utc", "2000-01-01T00:00:00Z")).replace("Z", "+00:00"))
    if (jetzt() - letzter).days >= 7:
        log("ACCESS_BLOCKED: wöchentlicher Testabruf"); return True
    return False

def revisionen_pruefen():
    """Einmal im Monat: letzte 8 Quartale per HEAD auf geänderte Grösse prüfen; bei Änderung neu holen."""
    monat = jetzt().strftime("%Y-%m")
    if ZUG.get("revision_monat") == monat:
        return
    for key in sorted(HERKUNFT)[-8:]:
        h = HERKUNFT[key]
        try:
            time.sleep(PAUSE)
            with urllib.request.urlopen(urllib.request.Request(h["url"], headers=UA, method="HEAD"), timeout=60) as r:
                cl = r.headers.get("Content-Length")
        except urllib.error.HTTPError as e:
            if e.code == 403:
                raise Gesperrt(f"{h['url']} (HEAD) | 403")
            continue
        if cl and h.get("content_length") and cl != h["content_length"]:
            log(f"{key}: Grösse geändert ({h['content_length']} -> {cl}), wird neu geholt")
            man["hinweise"].append(f"{key} von der SEC revidiert, neu geholt")
            try:
                os.remove(f"{OUT}/zwischen/{key}.csv.gz")
            except FileNotFoundError:
                pass
    ZUG["revision_monat"] = monat

if __name__ == "__main__":
    os.makedirs(f"{OUT}/zwischen", exist_ok=True)
    fertig = True
    if not KONTAKT:
        man["hinweise"].append("GitHub-Secret SEC_USER_AGENT fehlt: es wird noch die noreply-Adresse gesendet")
    versuch = darf_versuchen()
    if not versuch:
        fertig = False
        man["fehler"] = (f"ACCESS_BLOCKED seit {ZUG.get('erster_403_utc')}: keine Abrufe bis zur Klärung mit webmaster@sec.gov "
                         f"(nächster Testabruf 7 Tage nach dem letzten)")
        log(man["fehler"])
    elif ZUG.get("status") == "ACCESS_BLOCKED":
        ZUG["letzter_test_utc"] = jetzt().strftime("%Y-%m-%dT%H:%M:%SZ")
    try:
        if versuch:
            revisionen_pruefen()
        for y, q in (quartale() if versuch else []):
            if zeit_um():
                fertig = False; man["hinweise"].append("Zeitbudget: weitere Quartale im nächsten Lauf"); break
            res = quartal_verarbeiten(y, q)
            if res != "vorhanden":
                log(f"{y}q{q}: {res}")
            if res == "nicht publiziert":
                man["hinweise"].append(f"{y}q{q} noch nicht publiziert")
    except Gesperrt as e:
        fertig = False; sperre_melden(e)
    except Exception as e:
        fertig = False; man["fehler"] = str(e)[:300]; log(f"Fehler Quartale: {e}")
    try:
        ciks = set()
        for f in os.listdir(f"{OUT}/zwischen"):
            ciks |= {r["cik"] for r in lies(f"{OUT}/zwischen/{f}")}
        gesperrt = (not versuch) or ZUG.get("status") != "ok" and "403" in man.get("fehler", "")
        cache, offen = ({}, len(ciks)) if gesperrt else sic_nachfuehren(ciks)
        if versuch and not gesperrt and (HERKUNFT or ciks):
            zugang_ok()
        if offen:
            fertig = False; man["hinweise"].append(f"SIC: {offen} Emittenten noch offen")
        if not cache and os.path.exists(f"{OUT}/sic_cache.json"):
            cache = json.load(open(f"{OUT}/sic_cache.json"))
        if ciks:
            status, abd = reihen_schreiben(cache, fertig)
            log(f"Status {status}, Abdeckung Kaufwert mit Sektor {abd:.1%}")
    except Gesperrt as e:
        sperre_melden(e)
    except Exception as e:
        man["fehler"] = (man.get("fehler", "") + " | " + str(e)[:300]).strip(" |"); log(f"Fehler: {e}")
    man["zugang"] = {k: ZUG.get(k) for k in ("status", "erster_403_utc", "anzahl_403", "runner_ip", "kontakt_aus_secret")}
    json.dump(ZUG, open(f"{OUT}/zugang.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    json.dump(HERKUNFT, open(f"{OUT}/herkunft.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, sort_keys=True)
    json.dump(man, open(f"{OUT}/manifest_sec.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
