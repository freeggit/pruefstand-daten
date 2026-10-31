"""Tests zu discovery.py (V3.18, E9 Stufe 2; Fassung 2 vom 28.10.2026; Ergänzung vom 31.10.2026 zu §3 Ziff. 1 und 7).
Aufruf: python test_discovery.py – ohne Netz, im Wegwerf-Ordner."""
import gzip, json, os, sys, tempfile
from datetime import date, datetime, timedelta, timezone

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discovery as d  # noqa: E402

# Die Tests bis zum Abschnitt «Ergänzung vom 31.10.2026» prüfen Einfrieren, Nachführung und Einfrierprüfung wie bisher
# (Einfrieren bei der ersten Verwendung, PS_DISCOVERY_BESTAETIGUNGEN=0); die Aufnahme nach Bestätigungen folgt am Schluss.
os.environ["PS_DISCOVERY_BESTAETIGUNGEN"] = "0"


def ok(b, name):
    assert b, name
    print("ok ", name)


# ---------------------------------------------------------------- Kürzen (Datumsspalte je Quelle wie in suchmaschine.py)
kurs = (b"Date,Open,High,Low,Close,Volume,AdjClose\r\n2020-12-30,1.0,1,1,1.0,10,0.9\r\n2020-12-31,2.0,2,2,2.0,10,1.8\r\n"
        b"2021-01-04,3.0,3,3,3.0,10,2.7\r\n2026-10-23,5,5,5,5,5,5\r\n")
k, info = d.kuerzen(kurs, "kurse__spy_d.csv")
ok(k == b"Date,Open,High,Low,Close,Volume,AdjClose\r\n2020-12-30,1.0,1,1,1.0,10,0.9\r\n2020-12-31,2.0,2,2,2.0,10,1.8\r\n"
   and info["sicher"] and info["zeilen"] == 2 and info["weg"] == 2, "Kurse: Zeilen bis 31.12.2020 Byte für Byte, spätere weg")

fred = b"observation_date,SP500\r\n2016-10-27,2133.04\r\n2020-12-31,3756.07\r\n2021-01-04,3700.65\r\n"
ok(d.kuerzen(fred, "fred__SP500.csv")[0] == b"observation_date,SP500\r\n2016-10-27,2133.04\r\n2020-12-31,3756.07\r\n", "FRED: erste Spalte als Datum")

stunde = b"zeit_utc,preis\n2020-12-31T23:00Z,1\n2021-01-01T00:00Z,2\n"
ok(d.kuerzen(stunde, "e__hr__energie__preis_de_2021.csv")[0] == b"zeit_utc,preis\n2020-12-31T23:00Z,1\n", "Strom: ganzer Stichtag bleibt, 2021 weg")

gz = gzip.compress(stunde, mtime=5)
kg, _ = d.kuerzen(gz, "e__hr__energie__preis_de_2021.csv.gz")
ok(gzip.decompress(kg) == b"zeit_utc,preis\n2020-12-31T23:00Z,1\n" and kg == d.kuerzen(gzip.compress(stunde, mtime=99), "e__hr__energie__x.csv.gz")[0],
   "Gzip: gekürzt und unabhängig von mtime gleich gepackt")
ok(d.inhalt_sha(gzip.compress(b"abc", mtime=1), "x.gz") == d.inhalt_sha(gzip.compress(b"abc", compresslevel=1, mtime=2), "x.gz"),
   "Inhalt-Prüfsumme unabhängig von der Gzip-Fassung")

french = (b"This file was created using the 202608 CRSP database.\r\n\r\n,Mkt-RF,RF\r\n19261102,0.1,0.01\r\n20201231,0.2,0.0\r\n"
          b"20210104,0.3,0.0\r\n\r\nCopyright 2026 Eugene F. Fama and Kenneth R. French\r\n")
ok(d.kuerzen(french, "french__F-F_Research_Data_Factors_daily.csv")[0] ==
   b"This file was created using the 202608 CRSP database.\r\n\r\n,Mkt-RF,RF\r\n19261102,0.1,0.01\r\n20201231,0.2,0.0\r\n\r\nCopyright 2026 Eugene F. Fama and Kenneth R. French\r\n",
   "Ken French: Tage nach dem Stichtag weg, Kopf und Schluss bleiben")
ok(d.kuerzen(b"x\n,A\n202012,1\n202101,2\n2020,3\n2021,4\n", "french__F-F_Momentum_Factor.csv")[0] == b"x\n,A\n202012,1\n2020,3\n",
   "Ken French: Monate und Jahre nach dem Stichtag weg")

ok(d.kuerzen(b"timestamp,close\n1609459199,29000\n1609459200,29001\n", "btc.csv")[0] == b"timestamp,close\n1609459199,29000\n",
   "Bitcoin: Unix-Sekunden bis 31.12.2020 23:59:59")
ok(d.kuerzen(b"zeit,wasserstand_cm\r\n2026-10-26T09:45+01:00,120\r\n", "hr__pegel__kaub_2026.csv")[0] == b"zeit,wasserstand_cm\r\n",
   "Pegel (Spalte zeit): nur Kopf")
ok(d.kuerzen(b"datum,wert\n2020-12-31,1\n2021-01-01,2\n", "n__neu__x__y.csv")[0] == b"datum,wert\n2020-12-31,1\n", "Scout: Spalte datum")

for roh, name, grund in ((b"Date,wert\n2020/12/31,1\n", "kurse__x_d.csv", "Datum nicht lesbar"),
                         (b'datum,text,wert\n2019-01-01,"a,b",1\n2021-01-01,c,2\n', "n__neu__q__r.csv", "Anführungszeichen"),
                         (b"date,wert\n2021-01-01,1\n", "n__neu__q__r.csv", "Datumsspalte datum fehlt"),
                         (b"datum,wert\n2021-01-01,1\n", "neu_unbekannt.csv", "Quelle unbekannt"),
                         (b"timestamp,close\nx,1\n", "btc.csv", "Zeitstempel nicht lesbar")):
    r, i = d.kuerzen(roh, name)
    ok(r == roh and not i["sicher"] and i["grund"].startswith(grund), f"nicht sicher kürzbar ({grund}): ungekürzt, nicht eingefroren")
ok(d.pruefe_inhalt(k, "kurse__spy_d.csv") == (True, None) and not d.pruefe_inhalt(kurs, "kurse__spy_d.csv")[0], "pruefe_inhalt: Zeile nach dem Stichtag fällt auf")


# ---------------------------------------------------------------- Stand
def holen(b):
    return lambda: b


def fehler():
    raise OSError("Spiegel nicht lesbar")


def verz(stand):
    return json.load(open(os.path.join(stand, "stand.json")))


with tempfile.TemporaryDirectory() as tmp:
    stand, cache = os.path.join(tmp, "discovery"), os.path.join(tmp, "c")
    os.makedirs(cache)
    s = d.Stand(stand, schreiben=True, bericht=True, lauf_id="L1")
    s.bereitstellen("kurse__spy_d.csv", holen(kurs), os.path.join(cache, "a"))
    ok(not os.path.exists(os.path.join(stand, "stand.json")) and not os.path.exists(os.path.join(stand, "dateien")),
       "vor abschliessen: nichts abgelegt (Abbruch lässt den Stand unverändert)")
    b = s.abschliessen()
    v = verz(stand)
    e = v["dateien"]["kurse__spy_d.csv"]
    ok(open(os.path.join(cache, "a"), "rb").read() == k and b["neu_eingefroren"] == ["kurse__spy_d.csv"] and e["sha"] == d.sha(k)
       and e["datei"] == "kurse__spy_d.csv@" + d.sha(k)[:16] and os.path.exists(os.path.join(stand, "dateien", e["datei"])) and e["lauf_id"] == "L1",
       "neue Datei: gekürzt bereitgestellt, als Fassung mit Prüfsumme eingefroren")

    s0 = d.Stand(stand, schreiben=True)
    s0.bereitstellen("n__neu__q__r.csv", holen(b'datum,text,wert\n2019-01-01,"a,b",1\n'), os.path.join(cache, "q"))
    b0 = s0.abschliessen()
    ok(open(os.path.join(cache, "q"), "rb").read() == b'datum,text,wert\n2019-01-01,"a,b",1\n' and b0["nicht_eingefroren"][0]["datei"] == "n__neu__q__r.csv"
       and "n__neu__q__r.csv" not in verz(stand)["dateien"], "nicht sicher kürzbare neue Datei: ungekürzt gelesen, gemeldet, nicht eingefroren")

    revidiert = kurs.replace(b"2020-12-30,1.0,1,1,1.0,10,0.9", b"2020-12-30,1.0,1,1,1.0,10,0.90001")
    s2 = d.Stand(stand, schreiben=True, bericht=True, lauf_id="L2")
    s2.bereitstellen("kurse__spy_d.csv", holen(revidiert), os.path.join(cache, "b"))
    b2 = s2.abschliessen()
    r = b2["revisionen"][0]
    ok(open(os.path.join(cache, "b"), "rb").read() == k and b2["revisionen_n"] == 1 and r["geaendert"] == 1
       and r["erstes_datum"] == "2020-12-30" and 1e-5 < r["max_rel_abweichung"] < 2e-5 and verz(stand)["dateien"]["kurse__spy_d.csv"]["lauf_id"] == "L1",
       "Revision im Spiegel: Stand gilt weiter, Bericht mit Datum und Grösse")
    ok(b2["revisionen_summe"] == {"geaendert": 1, "hinzugekommen": 0, "entfallen": 0, "werte_fehlen_im_spiegel": 0,
                                  "werte_neu_im_spiegel": 0, "relativ_nicht_definiert": 0}, "Gutachten 23 (Soll): Summen im Bericht")

    nf = os.path.join(tmp, "nachfuehrung.json")
    json.dump({"eintraege": [{"id": "N0001", "dateien": ["kurse__spy_*"], "grund": "Test", "freigabe": "Test"},
                             {"id": "N0002", "dateien": ["fred__*"], "grund": "ohne Freigabe"},
                             {"id": "N0003", "dateien": "kurse__spy_d.csv", "grund": "Text statt Liste", "freigabe": "Test"},
                             {"id": "N0004", "dateien": ["gibt_es_nicht*"], "grund": "Test", "freigabe": "Test"}]}, open(nf, "w"))
    s3 = d.Stand(stand, schreiben=True, bericht=True, nachfuehrung=nf, lauf_id="L3")
    s3.bereitstellen("kurse__spy_d.csv", holen(revidiert), os.path.join(cache, "c"))
    b3 = s3.abschliessen()
    neu_k = d.kuerzen(revidiert, "kurse__spy_d.csv")[0]
    v3 = verz(stand)
    ok(open(os.path.join(cache, "c"), "rb").read() == neu_k and v3["dateien"]["kurse__spy_d.csv"]["sha"] == d.sha(neu_k)
       and v3["dateien"]["kurse__spy_d.csv"]["nachfuehrung"] == "N0001" and b3["nachfuehrung_angewandt"] == ["N0001"]
       and v3["nachfuehrungen"]["N0001"]["vollstaendig"] and not os.path.exists(os.path.join(stand, "dateien", e["datei"])),
       "Nachführung: Revision übernommen, vermerkt, alte Fassung entfernt")
    fe = {x["id"] for x in b3["nachfuehrung_fehler"]}
    ok({"N0002", "N0003", "N0004"} <= fe and "N0002" not in v3["nachfuehrungen"] and "N0003" not in v3["nachfuehrungen"]
       and not v3["nachfuehrungen"]["N0004"]["vollstaendig"], "fehlerhafte Einträge: nicht angewandt, gemeldet")

    s4 = d.Stand(stand, schreiben=True, bericht=True, nachfuehrung=nf, lauf_id="L4")
    s4.bereitstellen("kurse__spy_d.csv", holen(kurs), os.path.join(cache, "d"))
    b4 = s4.abschliessen()
    ok(open(os.path.join(cache, "d"), "rb").read() == neu_k and not b4["nachfuehrung_angewandt"] and b4["revisionen_n"] == 1,
       "Nachführung wirkt je Datei genau einmal; danach wieder eingefroren")

    s5 = d.Stand(stand, schreiben=False)
    s5.bereitstellen("fred__SP500.csv", holen(fred), os.path.join(cache, "e"))
    b5 = s5.abschliessen()
    ok(b5["nur_gelesen_nicht_eingefroren"] == ["fred__SP500.csv"] and "fred__SP500.csv" not in verz(stand)["dateien"],
       "nur lesend (Familie V): gekürzt, nicht eingefroren")

    ok(not d.pruefen(stand)["verstoesse"], "Einfrierprüfung: bestanden")
    q = os.path.join(stand, "dateien", verz(stand)["dateien"]["kurse__spy_d.csv"]["datei"])
    open(q, "wb").write(neu_k + b"2021-01-04,3,3,3,3,10,2.7\r\n")
    ok(any("Prüfsumme" in x["grund"] for x in d.pruefen(stand)["verstoesse"]), "Einfrierprüfung: veränderte Datei fällt auf")
    v = verz(stand)
    v["dateien"]["kurse__spy_d.csv"].update(sha=d.sha(open(q, "rb").read()), sha_inhalt=d.inhalt_sha(open(q, "rb").read(), "x"))
    json.dump(v, open(os.path.join(stand, "stand.json"), "w"))
    ok(any("nach dem Stichtag" in x["grund"] for x in d.pruefen(stand)["verstoesse"]), "Einfrierprüfung: Zeile nach dem Stichtag fällt auf")
    os.remove(q)
    ok(any(x["grund"] == "fehlt" for x in d.pruefen(stand)["verstoesse"]), "Einfrierprüfung: fehlende Datei fällt auf")
    try:
        d.Stand(stand, schreiben=True).bereitstellen("kurse__spy_d.csv", holen(kurs), os.path.join(cache, "f"))
        ok(False, "fehlende Datei muss abbrechen")
    except RuntimeError as ex:
        ok("beschädigt" in str(ex), "fehlende Datei ohne Nachführung: Abbruch statt stilles Neu-Einfrieren")

    json.dump({"eintraege": [{"id": "N0005", "dateien": ["kurse__spy_d.csv"], "grund": "Reparatur", "freigabe": "Test"}]}, open(nf, "w"))
    s6 = d.Stand(stand, schreiben=True, nachfuehrung=nf, lauf_id="L6")
    try:
        s6.bereitstellen("kurse__spy_d.csv", fehler, os.path.join(cache, "g"))
        ok(False, "Spiegel nicht lesbar und alte Fassung fehlt: muss abbrechen")
    except RuntimeError:
        pass
    s6.abschliessen()
    ok(not verz(stand)["nachfuehrungen"]["N0005"]["vollstaendig"], "Nachführung bei unlesbarem Spiegel: bleibt offen")
    s7 = d.Stand(stand, schreiben=True, nachfuehrung=nf, lauf_id="L7")
    s7.bereitstellen("kurse__spy_d.csv", holen(kurs), os.path.join(cache, "h"))
    s7.abschliessen()
    ok(not d.pruefen(stand)["verstoesse"] and verz(stand)["nachfuehrungen"]["N0005"]["vollstaendig"],
       "Nachführung repariert eine fehlende Fassung; Einfrierprüfung wieder bestanden")

with tempfile.TemporaryDirectory() as tmp:   # nicht gelesene Datei: Befund statt Verstoss; Muster nur auf Dateien vom ersten Anwenden
    stand, cache = os.path.join(tmp, "discovery"), os.path.join(tmp, "c")
    os.makedirs(cache)
    s = d.Stand(stand, schreiben=True)
    s.bereitstellen("kurse__aaa_d.csv", holen(kurs), os.path.join(cache, "1"))
    s.bereitstellen("kurse__bbb_d.csv", holen(kurs), os.path.join(cache, "2"))
    s.abschliessen()
    os.remove(os.path.join(stand, "dateien", verz(stand)["dateien"]["kurse__bbb_d.csv"]["datei"]))
    p = d.pruefen(stand, gelesen={"kurse__aaa_d.csv"})
    ok(not p["verstoesse"] and p["befunde_nicht_gelesen"][0]["datei"] == "kurse__bbb_d.csv",
       "Einfrierprüfung: Mangel an nicht gelesener Datei ist Befund, hält den Lauf nicht an")
    ok(d.pruefen(stand, gelesen={"kurse__bbb_d.csv"})["verstoesse"] and d.pruefen(stand)["verstoesse"],
       "Einfrierprüfung: Mangel an gelesener Datei (oder ohne Liste) ist Verstoss")
    nf = os.path.join(tmp, "n.json")
    json.dump({"eintraege": [{"id": "N1", "dateien": ["kurse__*"], "grund": "Test", "freigabe": "Test"}]}, open(nf, "w"))
    s = d.Stand(stand, schreiben=True, nachfuehrung=nf)
    s.bereitstellen("kurse__aaa_d.csv", holen(revidiert), os.path.join(cache, "3"))
    s.bereitstellen("kurse__ccc_d.csv", holen(kurs), os.path.join(cache, "4"))
    s.abschliessen()
    n1 = verz(stand)["nachfuehrungen"]["N1"]
    ok(n1["gemeint"] == ["kurse__aaa_d.csv", "kurse__bbb_d.csv"] and n1["offen"] == ["kurse__bbb_d.csv"] and "kurse__ccc_d.csv" not in n1["gemeint"],
       "Nachführung: später eingefrorene Datei gehört nicht zum Eintrag")
    s = d.Stand(stand, schreiben=True, nachfuehrung=nf)
    s.bereitstellen("kurse__ccc_d.csv", holen(revidiert), os.path.join(cache, "5"))
    s.abschliessen()
    ok(open(os.path.join(cache, "5"), "rb").read() == k, "Nachführung: später eingefrorene Datei bleibt eingefroren")

# ---------------------------------------------------------------- Gutachten 23 (Soll): Revisionsbericht
a_ = b"observation_date,X\n2020-01-01,1.0\n2020-01-02,2.0\n2020-01-03,3.0\n2020-01-06,0\n"
b_ = b"observation_date,X\n2020-01-01,1.5\n2020-01-02,.\n2020-01-06,0.25\n2020-01-07,4.0\n"
u_ = d.unterschied(a_, b_, "fred__X.csv")
ok(u_["geaendert"] == 3 and u_["hinzugekommen"] == 1 and u_["entfallen"] == 1, "Revisionsbericht: geändert, hinzugekommen, entfallen")
ok(u_["werte_fehlen_im_spiegel"] == 1 and u_["werte_neu_im_spiegel"] == 0, "Revisionsbericht: fehlende Werte gesondert (FRED «.»)")
ok(u_["relativ_nicht_definiert"] == 1 and u_["max_abs_abweichung_bei_null"] == 0.25 and u_["max_rel_abweichung"] == 0.5
   and u_["max_abs_abweichung"] == 0.5, "Revisionsbericht: Bezugswert null nur absolut, relativ nicht definiert")
u2_ = d.unterschied(b_, a_, "fred__X.csv")
ok(u2_["werte_neu_im_spiegel"] == 1 and u2_["hinzugekommen"] == 1 and u2_["entfallen"] == 1, "Revisionsbericht: Wert neu vorhanden")

fa = b"This file was created using the 202608 CRSP database.\r\n\r\n,Mkt-RF,SMB\r\n19260701,0.10,-0.25\r\n20201230,0.50,0.10\r\n"
fb = b"This file was created using the 202609 CRSP database.\r\n\r\n,Mkt-RF,SMB\r\n19260701,0.10,-0.25\r\n20201230,0.51,0.10\r\n"
u3_ = d.unterschied(fa, fb, "french__F-F_Research_Data_Factors_daily.csv")
ok(u3_["kopf_geaendert"] and u3_["geaendert"] == 1 and u3_["hinzugekommen"] == 0 and u3_["entfallen"] == 0
   and u3_["erstes_datum"] == "20201230", "Revisionsbericht Ken French: Textzeilen als Kopf, nicht als Daten")

ok(d.AKTIV is True, "Schalter AKTIV (Rückweg) vorhanden und eingeschaltet")

# ---------------------------------------------------------------- Ergänzung vom 31.10.2026: Aufnahme nach zwei Bestätigungen
ok(d.kennzahl(k, "kurse__spy_d.csv") == (2, "2020-12-30"), "Kennzahl Kurse: Zeilen mit Werten, erstes Datum")
ok(d.kennzahl(d.kuerzen(french, "french__F-F_Research_Data_Factors_daily.csv")[0], "french__F-F_Research_Data_Factors_daily.csv")
   == (2, "1926-11-02"), "Kennzahl Ken French: Datumszeilen bis zum Stichtag")
ok(d.kennzahl(b"timestamp,close\n1609459199,29000\n", "btc.csv") == (1, "2020-12-31"), "Kennzahl Bitcoin: Unix-Sekunden")
ok(d.kennzahl(b"observation_date,X\n2020-01-01,.\n2020-01-02,0\n2020-01-03,1.5\n2020-01-06,nan\n", "fred__X.csv") == (1, "2020-01-01"),
   "Kennzahl: fehlende Werte («.», NaN) und 0 zählen nicht")

os.environ.pop("PS_DISCOVERY_BESTAETIGUNGEN", None)
ok(d.Stand(tempfile.mkdtemp()).bestaetigungen == 2, "ohne Variable: zwei Bestätigungen (Regel der Suche)")
os.environ["PS_DISCOVERY_BESTAETIGUNGEN"] = "0"
ok(d.Stand(tempfile.mkdtemp()).bestaetigungen == 0, "PS_DISCOVERY_BESTAETIGUNGEN=0: Einfrieren bei der ersten Verwendung (Siegeltest)")
os.environ.pop("PS_DISCOVERY_BESTAETIGUNGEN", None)

UHR = [None]
d._jetzt = lambda: UHR[0]


def um(h):
    """Uhr der Läufe: h Stunden nach dem 1.11.2026, 05:00 UTC."""
    UHR[0] = (datetime(2026, 11, 1, 5, tzinfo=timezone.utc) + timedelta(hours=h)).strftime("%Y-%m-%dT%H:%M:%SZ")


def termine(fehlen=(), beginn="2019-01-01"):
    """Scout-Terminreihe wie USDA: jeder Kalendertag bis 10.1.2021, 1 am 10. jedes Monats (24 Termine bis 2020)."""
    t0 = date.fromisoformat(beginn)
    z = ["datum,wert"]
    for i in range((date(2021, 1, 10) - t0).days + 1):
        t = t0 + timedelta(days=i)
        z.append(f"{t.isoformat()},{1 if t.day == 10 and t.isoformat() not in fehlen else 0}")
    return gzip.compress(("\n".join(z) + "\n").encode(), mtime=0)


voll = termine()
kurz = termine(fehlen=("2019-03-10", "2019-07-10", "2020-02-10"))        # verkürzter Abruf: 21 statt 24 Termine
N = "n__neu__usda__wasde.csv.gz"
ok(d.kennzahl(d.kuerzen(voll, N)[0], N) == (24, "2019-01-01") and d.kennzahl(d.kuerzen(kurz, N)[0], N)[0] == 21,
   "Kennzahl Terminreihe: Termine, nicht Zeilen (verkürzt: gleiche Zeilenzahl, weniger Termine)")


def lauf(stand, cache, dateien, h, lauf_id, schreiben=True, bericht=True, **kw):
    um(h)
    s = d.Stand(stand, schreiben=schreiben, bericht=bericht, lauf_id=lauf_id, **kw)
    for name, roh in dateien.items():
        s.bereitstellen(name, holen(roh), os.path.join(cache, f"{lauf_id}_{name}"))
    return s.abschliessen()


with tempfile.TemporaryDirectory() as tmp:
    stand, cache = os.path.join(tmp, "discovery"), os.path.join(tmp, "c")
    os.makedirs(cache)
    b = lauf(stand, cache, {N: voll}, 0, "R1")
    v = verz(stand)
    ok(N not in v["dateien"] and N in v["vorgemerkt"] and b["vorgemerkt_neu"][0]["datei"] == N and not b["neu_eingefroren"]
       and open(os.path.join(cache, f"R1_{N}"), "rb").read() == d.kuerzen(voll, N)[0] and b["vorgemerkt_n"] == 1,
       "neue Datei: vorgemerkt, gekürzt aus dem Spiegel gelesen, nicht eingefroren")
    vorher = open(os.path.join(stand, "stand.json"), "rb").read()
    b = lauf(stand, cache, {N: voll}, 5, "R2")
    ok(open(os.path.join(stand, "stand.json"), "rb").read() == vorher and not b["bestaetigung"] and N not in verz(stand)["dateien"],
       "Lauf nach 5 Stunden: zählt nicht, Stand unverändert")
    b = lauf(stand, cache, {N: voll}, 24, "R3")
    ok(b["bestaetigung"] == [{"datei": N, "sichtung": 2, "von": 3, "werte": 24, "beste_werte": 24, "eingefroren": False}]
       and N not in verz(stand)["dateien"], "erste Bestätigung nach 24 Stunden: noch nicht eingefroren")
    b = lauf(stand, cache, {N: voll}, 48, "R4")
    v = verz(stand)
    ok(N in v["dateien"] and N not in v["vorgemerkt"] and b["neu_eingefroren"] == [N] and b["bestaetigung"][0]["eingefroren"]
       and v["dateien"][N]["sha"] == d.sha(d.kuerzen(voll, N)[0]) and v["dateien"][N]["lauf_id"] == "R4" and not d.pruefen(stand)["verstoesse"],
       "zweite Bestätigung nach 48 Stunden: jüngste Fassung eingefroren, Einfrierprüfung bestanden")

    G = "n__neu__usda__grain.csv.gz"                                      # USDA-Fall: verkürzt bei der ersten Sichtung
    lauf(stand, cache, {G: kurz}, 0, "G1")
    b = lauf(stand, cache, {G: voll}, 24, "G2")
    ok(G not in verz(stand)["dateien"] and b["zurueckgehalten"][0]["datei"] == G and b["zurueckgehalten"][0]["werte"] == 21
       and b["zurueckgehalten"][0]["beste_werte"] == 24, "verkürzte erste Sichtung: zurückgehalten, sobald die vollständige Fassung erscheint")
    lauf(stand, cache, {G: voll}, 48, "G3")
    ok(G not in verz(stand)["dateien"], "ein Rückgang verlangt danach drei gute Sichtungen")
    b = lauf(stand, cache, {G: voll}, 72, "G4")
    ok(verz(stand)["dateien"][G]["sha"] == d.sha(d.kuerzen(voll, G)[0]) and b["neu_eingefroren"] == [G],
       "USDA-Fall: eingefroren wird die vollständige Fassung (24 Termine), nicht die verkürzte")

    X = "n__neu__fda__zulassungen.csv.gz"                                 # Rückgang zwischen zwei Sichtungen (unter 20 h)
    lauf(stand, cache, {X: voll}, 0, "X1")
    b = lauf(stand, cache, {X: kurz}, 3, "X2")
    e = verz(stand)["vorgemerkt"][X]
    ok(len(e["sichtungen"]) == 1 and e["sichtungen"][0]["werte"] == 21 and e["beste_werte"] == 24 and b["zurueckgehalten"][0]["datei"] == X,
       "Rückgang nach 3 Stunden: ersetzt die letzte Sichtung, zurückgehalten")
    for h, lid in ((24, "X3"), (48, "X4")):
        lauf(stand, cache, {X: voll}, h, lid)
    ok(X not in verz(stand)["dateien"], "nach dem Rückgang: zwei gute Sichtungen genügen nicht")
    lauf(stand, cache, {X: voll}, 72, "X5")
    ok(X in verz(stand)["dateien"], "nach dem Rückgang: drei gute Sichtungen, eingefroren")

    Y = "n__neu__norges__ziel.csv.gz"                                     # erstes Datum später, ohne Verlust von Terminen
    y0 = termine(fehlen={f"2019-{m:02d}-10" for m in range(1, 6)})
    y1 = termine(fehlen={f"2019-{m:02d}-10" for m in range(1, 6)}, beginn="2019-03-01")
    y2 = termine(fehlen={f"2019-{m:02d}-10" for m in range(1, 6)}, beginn="2019-01-03")
    lauf(stand, cache, {Y: y0}, 0, "Y1")
    b = lauf(stand, cache, {Y: y1}, 24, "Y2")
    ok(b["zurueckgehalten"] and b["zurueckgehalten"][0]["grund"].startswith("erstes Datum"), "erstes Datum 59 Tage später: zurückgehalten")
    Z = "n__neu__rollend__x.csv.gz"                                       # Rollfenster: Beginn 2 Tage später ist erlaubt
    lauf(stand, cache, {Z: y0}, 0, "Z1")
    lauf(stand, cache, {Z: y2}, 24, "Z2")
    lauf(stand, cache, {Z: y2}, 48, "Z3")
    ok(Z in verz(stand)["dateien"], "Rollfenster (Beginn 2 Tage später, keine Termine verloren): eingefroren")

    W_ = "n__neu__wackel__w.csv.gz"                                       # schwankt dauernd: Befund nach 7 Tagen
    for t in range(0, 9):
        b = lauf(stand, cache, {W_: voll if t % 2 == 0 else kurz}, 24 * t, f"W{t}")
    ok(W_ not in verz(stand)["dateien"] and b["vorgemerkt_ueber_7_tage"] == [W_], "dauernd schwankende Datei: nie eingefroren, Befund nach 7 Tagen")

    F = "n__neu__familie__v.csv.gz"
    b = lauf(stand, cache, {F: voll}, 300, "V1", schreiben=False)
    ok(b["nur_gelesen_nicht_eingefroren"] == [F] and F not in (verz(stand).get("vorgemerkt") or {}), "Familie V (nur lesend): nicht vorgemerkt")
    ok(not d.pruefen(stand)["verstoesse"], "vorgemerkte Dateien stören die Einfrierprüfung nicht")

with tempfile.TemporaryDirectory() as tmp:                                # Warnung im Revisionsbericht (§3 Ziff. 7)
    stand, cache = os.path.join(tmp, "discovery"), os.path.join(tmp, "c")
    os.makedirs(cache)
    lauf(stand, cache, {N: kurz}, 0, "A1", bestaetigungen=0)              # verkürzt eingefroren wie am 28.10.2026
    b = lauf(stand, cache, {N: voll}, 24, "A2")
    r = b["revisionen"][0]
    ok(r["stand_unvollstaendig"] and r["werte_ungleich_null_stand"] == 21 and r["werte_ungleich_null_spiegel"] == 24
       and b["warnungen_stand_unvollstaendig"] == [{"datei": N, "werte_stand": 21, "werte_spiegel": 24}],
       "Stand mit weniger Terminen als der Spiegel: Warnung «Stand möglicherweise unvollständig»")
    viel = b"datum,wert\n" + b"".join(f"2020-{1 + i // 28:02d}-{1 + i % 28:02d},{1 + i % 5}\n".encode() for i in range(201))
    wenig = viel.replace(b"2020-01-05,5\n", b"2020-01-05,0\n")
    lauf(stand, cache, {"n__neu__klein__k.csv": wenig}, 48, "A3", bestaetigungen=0)
    b = lauf(stand, cache, {"n__neu__klein__k.csv": viel}, 72, "A4")
    ok(not b["revisionen"][0]["stand_unvollstaendig"] and not b["warnungen_stand_unvollstaendig"],
       "Stand mit 200 statt 201 Werten (unter 1%): keine Warnung, nur Revision")
    b = lauf(stand, cache, {N: kurz}, 96, "A5")
    ok(b["revisionen_n"] == 0 and not b["warnungen_stand_unvollstaendig"], "Spiegel gleich wie Stand: keine Revision, keine Warnung")

print("alle Tests bestanden")
