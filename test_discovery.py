"""Tests zu discovery.py (V3.18, E9 Stufe 2; ENTWURF 27.10.2026, Fassung 2 vom 28.10.2026). Aufruf: python test_discovery.py – ohne Netz, im Wegwerf-Ordner."""
import gzip, json, os, sys, tempfile

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import discovery as d  # noqa: E402


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
print("alle Tests bestanden")
