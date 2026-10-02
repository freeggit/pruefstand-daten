"""Tests für fetch_six.py ohne Netz (nachgestellte Quelle). Aufruf: python test_fetch_six.py"""
import gzip, json, os, tempfile, urllib.error
from datetime import datetime, timezone
import fetch_six as f

def quelle(mt, bt, kappe=None, fehler_bei=None):
    def hole(url):
        art = "mt" if "management_transactions" in url else "bt"
        q = dict(p.split("=") for p in url.split("?")[1].split("&"))
        if fehler_bei == art:
            raise urllib.error.HTTPError(url, 403, "Forbidden", {}, None)
        daten = mt if art == "mt" else bt
        feld = f.ARTEN[art]["datum"]
        treffer = [m for m in daten if q["fromDate"] <= str(m[feld]) <= q["toDate"]]
        treffer.sort(key=lambda m: -m[feld])
        gr = min(int(q["pageSize"]), kappe or 10**9); s = int(q["pageNumber"])
        return {"status": "Ok", "totalCount": len(treffer), "itemList": treffer[s * gr:(s + 1) * gr]}
    return hole

def zeilen(out, art, jahr):
    return [json.loads(z) for z in gzip.open(os.path.join(out, art, f"{jahr}.jsonl.gz"), "rt", encoding="utf-8")]

mt = [{"notificationId": f"T{i:04d}", "transactionDate": 20230101 + (i % 28) + 10000 * (i % 3), "ISIN": "CH0000000001",
       "transactionAmountCHF": 100.0 * i, "buySellIndicator": "1", "notificationSubmitter": "Muster AG"} for i in range(250)]
bt = [{"notificationId": "ZA-1", "publicationDate": 20260930, "notificationSubmitter": "Muster AG",
       "beneficialNames": ["Hans Muster", "Fonds X"], "groupRepresentative": "Hans Muster, Zug", "positionVotingRate": "5.1",
       "holders": [{"holderName": "Hans Muster", "rate": 3.0}]}]
with tempfile.TemporaryDirectory() as out:
    t1 = datetime(2026, 10, 3, 3, 20, tzinfo=timezone.utc)
    st = f.lauf(out, quelle(mt, bt, kappe=50), pause=0, zeit=t1)          # Quelle liefert höchstens 50 je Seite
    assert st["mt"]["bestand_anzahl"] == 250 and st["mt"]["meldungen"] == 250 and st["mt"]["letzter_fehler"] is None, st["mt"]
    alle = sum((zeilen(out, "mt", j) for j in (2023, 2024, 2025)), [])
    assert len(alle) == 250 and all(z["nachgeladen"] and z["fassung"] == 1 for z in alle); print("ok  Bestand vollständig trotz kleiner Seiten; als nachgeladen markiert")
    z = zeilen(out, "bt", 2026)[0]; txt = json.dumps(z, ensure_ascii=False)
    assert "Hans Muster" not in txt and "Fonds X" not in txt and z["meldung"]["beneficialNames_n"] == 2 and z["meldung"]["holders"][0]["rate"] == 3.0 and z["meldung"]["notificationSubmitter"] == "Muster AG"
    print("ok  Beteiligungen: keine Namen gespeichert, Anzahl und Kennung vorhanden, Emittent bleibt")
    vor = open(os.path.join(out, "mt", "2023.jsonl.gz"), "rb").read()
    # zweiter Lauf: eine neue Meldung, eine geänderte (im Rückblickfenster), sonst nichts
    mt2 = mt + [{"notificationId": "T9001", "transactionDate": 20261002, "ISIN": "CH0000000002", "transactionAmountCHF": 5.0},
                {"notificationId": "T9002", "transactionDate": 20261001, "ISIN": "CH0000000003", "transactionAmountCHF": 7.0}]
    t2 = datetime(2026, 10, 4, 3, 20, tzinfo=timezone.utc)
    st = f.lauf(out, quelle(mt2, bt), pause=0, zeit=t2)
    assert st["mt"]["letzter_lauf_neu"] == 2 and st["bt"]["letzter_lauf_neu"] == 0
    neu = zeilen(out, "mt", 2026)
    assert all(not z["nachgeladen"] and z["erstmals_gesehen_utc"] == "2026-10-04T03:20:00Z" for z in neu)
    assert open(os.path.join(out, "mt", "2023.jsonl.gz"), "rb").read() == vor; print("ok  zweiter Lauf: 2 neue mit Zeitstempel, alte Dateien bitgleich")
    mt3 = [dict(m, transactionAmountCHF=8.0) if m["notificationId"] == "T9002" else m for m in mt2 if m["notificationId"] != "T9001"]
    st = f.lauf(out, quelle(mt3, bt), pause=0, zeit=datetime(2026, 10, 5, 3, 20, tzinfo=timezone.utc))
    z26 = zeilen(out, "mt", 2026)
    assert st["mt"]["letzter_lauf_geaendert"] == 1 and len(z26) == 3 and [z["fassung"] for z in z26 if z["id"] == "T9002"] == [1, 2]
    assert any(z["id"] == "T9001" for z in z26); print("ok  Änderung = neue Fassung, alte bleibt; verschwundene Meldung bleibt im Archiv")
    st = f.lauf(out, quelle(mt3, bt, fehler_bei="mt"), pause=0, zeit=datetime(2026, 10, 6, 3, 20, tzinfo=timezone.utc))
    assert st["mt"]["letzter_fehler"].startswith("HTTP 403") and st["mt"]["fehler_seit_utc"] and st["bt"]["laeufe"] == 3 and len(zeilen(out, "mt", 2026)) == 3
    print("ok  Sperre 403: Befund im Stand, kein weiterer Abruf, Archiv unverändert")
    def kaputt(url):
        return {"status": "Ok", "totalCount": 500, "itemList": mt[:50]}
    m, tot, feh = f.abrufen("mt", "20000101", "20261231", kaputt, 0)
    assert len(m) == 50 and "wiederholt" in feh; print("ok  Quelle blättert nicht: Fehler statt falscher Vollständigkeit")
with tempfile.TemporaryDirectory() as out:                                 # erster Lauf scheitert: Bestand nicht als geladen markiert
    st = f.lauf(out, quelle(mt, bt, fehler_bei="mt"), pause=0, zeit=datetime(2026, 10, 3, tzinfo=timezone.utc))
    assert "bestand_geladen_utc" not in st["mt"]; print("ok  gescheiterter Erstlauf zählt nicht als Bestand")
print("alle Tests bestanden")
