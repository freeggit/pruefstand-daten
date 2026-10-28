"""Tests zu lauf_status.py (V3.11, E29). Aufruf: python test_lauf_status.py – ohne Netz, im Wegwerf-Ordner."""
import json, os, subprocess, sys, tempfile

def lauf(tmp, env):
    e = dict(os.environ, PS_LERNEN_DIR=tmp, **env)
    for k in ("GITHUB_RUN_ID", "GITHUB_EVENT_NAME"):
        if k not in env:
            e.pop(k, None)
    r = subprocess.run([sys.executable, os.path.join(os.path.dirname(os.path.abspath(__file__)), "lauf_status.py")], env=e, capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout

def ok(b, name):
    assert b, name; print("ok ", name)

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lauf_status import pruef_hash, umgebung, PRUEF_DATEIEN  # noqa: E402
PH = pruef_hash(os.path.dirname(os.path.abspath(__file__)))

with tempfile.TemporaryDirectory() as tmp:   # 1 alles gelungen
    os.makedirs(os.path.join(tmp, "suche", "laeufe"))
    json.dump({"lauf_id": "L1", "github_run_id": "77", "stufen": {"suche": "vollständig", "analyse": "ausstehend", "familie_v": "ausstehend"},
               "ergebnis_hash": "e1", "ausgaben": {"vollarchiv_ergebnis_hash": "e1"}, "e9": {"eingabe_hash_lauf": "g1"}}, open(os.path.join(tmp, "suche", "laeufe", "L1.json"), "w"))
    json.dump({"lauf_id": "L1", "kandidaten": 5}, open(os.path.join(tmp, "suche", "letzter_lauf.json"), "w"))
    json.dump({"laeufe": [{"datei": "suche/laeufe/L1.json", "lauf_id": "L1"}], "pruefungen_bestanden": {"pruef_hash": PH, "lauf_id": "L0"}}, open(os.path.join(tmp, "index.json"), "w"))
    lauf(tmp, {"GITHUB_RUN_ID": "77", "STUFE_TESTS": "skipped", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "success", "STUFE_FAMILIE_V": "success"})
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L1.json"))); l = json.load(open(os.path.join(tmp, "suche", "letzter_lauf.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "vollständig" and e["stufen"]["analyse"] == "vollständig" and e["stufen"]["tests"] == "übersprungen", "alles gelungen: gesamt vollständig")
    ok(l["gesamt"] == "vollständig" and l["kandidaten"] == 5, "letzter_lauf.json nachgeführt, Inhalt bleibt")
    ok(i["laeufe"] == [{"datei": "suche/laeufe/L1.json", "lauf_id": "L1", "gesamt": "vollständig", "importierbar": True}], "index: kein Doppel, gesamt eingetragen")
    ok(e["e38"]["importierbar"] and e["e38"]["pruefungen"]["status"] == "bestanden für identischen Prüfstand", "E38: Nachweis aus früherem Lauf mit identischem Prüfstand")
    ok(i["letzter_eingabe_hash"] == "g1" and i["letzter_gueltiger_lauf"] == "L1", "E9: gültiger Lauf wird Referenz")

with tempfile.TemporaryDirectory() as tmp:   # 2 Analyse scheitert (continue-on-error): teilweise
    os.makedirs(os.path.join(tmp, "suche", "laeufe"))
    json.dump({"lauf_id": "L2", "github_run_id": "78", "stufen": {"suche": "vollständig"}}, open(os.path.join(tmp, "suche", "laeufe", "L2.json"), "w"))
    json.dump({"lauf_id": "L2"}, open(os.path.join(tmp, "suche", "letzter_lauf.json"), "w"))
    lauf(tmp, {"GITHUB_RUN_ID": "78", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "failure", "STUFE_FAMILIE_V": "success"})
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L2.json")))
    ok(e["gesamt"] == "teilweise" and e["stufen"]["analyse"] == "fehlgeschlagen", "Analyse fehlgeschlagen: gesamt teilweise")

with tempfile.TemporaryDirectory() as tmp:   # 3 Tests scheitern vor der Suche: Versuch wird trotzdem festgehalten, alter Stand bleibt erkennbar alt
    os.makedirs(os.path.join(tmp, "suche", "laeufe"))
    json.dump({"lauf_id": "L0", "github_run_id": "70", "stufen": {"suche": "vollständig"}, "gesamt": "vollständig"}, open(os.path.join(tmp, "suche", "laeufe", "L0.json"), "w"))
    json.dump({"lauf_id": "L0", "kandidaten": 5}, open(os.path.join(tmp, "suche", "letzter_lauf.json"), "w"))
    lauf(tmp, {"GITHUB_RUN_ID": "79", "GITHUB_EVENT_NAME": "push", "STUFE_TESTS": "failure", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "skipped", "STUFE_ANALYSE": "skipped", "STUFE_FAMILIE_V": "skipped"})
    neu = [n for n in os.listdir(os.path.join(tmp, "suche", "laeufe")) if n != "L0.json"]
    ok(len(neu) == 1, "gescheiterter Versuch erhält einen eigenen Laufeintrag")
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", neu[0]))); l = json.load(open(os.path.join(tmp, "suche", "letzter_lauf.json")))
    ok(e["gesamt"] == "fehlgeschlagen" and e["stufen"]["tests"] == "fehlgeschlagen" and e["stufen"]["analyse"] == "übersprungen", "Tests fehlgeschlagen: gesamt fehlgeschlagen")
    ok(l["lauf_id"] == "L0" and l["letzter_versuch"]["gesamt"] == "fehlgeschlagen", "letzter_lauf.json zeigt weiter L0 und nennt den gescheiterten Versuch")
    alt = json.load(open(os.path.join(tmp, "suche", "laeufe", "L0.json")))
    ok(alt["gesamt"] == "vollständig", "früherer Laufeintrag bleibt unverändert")

def fall(tmp, lauf, idx, env):
    os.makedirs(os.path.join(tmp, "suche", "laeufe"))
    json.dump(lauf, open(os.path.join(tmp, "suche", "laeufe", lauf["lauf_id"] + ".json"), "w"))
    json.dump({"lauf_id": lauf["lauf_id"]}, open(os.path.join(tmp, "suche", "letzter_lauf.json"), "w"))
    json.dump(idx, open(os.path.join(tmp, "index.json"), "w"))

ALLES = {"STUFE_TESTS": "skipped", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "success", "STUFE_FAMILIE_V": "success"}

with tempfile.TemporaryDirectory() as tmp:   # 4 V3.17 E38: Vollarchiv aus früherem Lauf passt nicht -> teilweise, keine Referenz
    fall(tmp, {"lauf_id": "L4", "github_run_id": "80", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "neu",
               "ausgaben": {"vollarchiv_ergebnis_hash": "alt"}, "e9": {"eingabe_hash_lauf": "g4"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH}, "letzter_eingabe_hash": "g3"}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="80"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L4.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "teilweise" and not e["e38"]["importierbar"] and not e["e38"]["archiv_passend"], "E38: fremdes Archiv -> teilweise, nicht importierbar")
    ok(i["letzter_eingabe_hash"] == "g3" and "letzter_gueltiger_lauf" not in i, "E9: ungültiger Lauf wird nicht Referenz")

with tempfile.TemporaryDirectory() as tmp:   # 5 V3.17 E38: Tests übersprungen, kein Nachweis für diesen Prüfstand -> teilweise
    fall(tmp, {"lauf_id": "L5", "github_run_id": "81", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "x",
               "ausgaben": {"vollarchiv_ergebnis_hash": "x"}}, {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": "anderer"}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="81"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L5.json")))
    ok(e["gesamt"] == "teilweise" and e["e38"]["pruefungen"]["status"] == "kein Nachweis für diesen Prüfstand", "E38: übersprungene Prüfung ohne Nachweis -> teilweise")

with tempfile.TemporaryDirectory() as tmp:   # 6 V3.17 E38: Tests und Siegeltest im Lauf bestanden -> Nachweis wird gespeichert
    fall(tmp, {"lauf_id": "L6", "github_run_id": "82", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "y",
               "ausgaben": {"vollarchiv_ergebnis_hash": "y"}, "e9": {"eingabe_hash_lauf": "g6"}}, {"laeufe": []}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="82", STUFE_TESTS="success", STUFE_SIEGELTEST="success"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L6.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "vollständig" and i["pruefungen_bestanden"]["pruef_hash"] == PH and i["pruefungen_bestanden"]["lauf_id"] == "L6",
       "E38: bestandene Prüfungen werden Nachweis")
    ok(i["pruefungen_bestanden"]["umgebung"] == umgebung() and e["e38"]["pruefungen"]["umgebung"] == umgebung(),
       "Gutachten 23 M4: Nachweis nennt die gebundene Rechenumgebung")

with tempfile.TemporaryDirectory() as tmp:   # 7 V3.17 E9: keine Neuberechnung ist weder Fehler noch Ergebnis
    fall(tmp, {"lauf_id": "L7", "github_run_id": "83", "stufen": {"suche": "keine Neuberechnung"}},
         {"laeufe": [], "letzter_eingabe_hash": "g", "letzter_gueltiger_lauf": "L6"}, {})
    lauf(tmp, {"GITHUB_RUN_ID": "83", "STUFE_TESTS": "skipped", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "skipped", "STUFE_FAMILIE_V": "skipped"})
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L7.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "keine Neuberechnung" and e["stufen"]["suche"] == "keine Neuberechnung" and not e["e38"]["importierbar"], "E9: Status keine Neuberechnung")
    ok(i["letzter_gueltiger_lauf"] == "L6" and i["letzter_eingabe_hash"] == "g", "E9: Referenz bleibt beim letzten gültigen Lauf")

with tempfile.TemporaryDirectory() as tmp:   # 8 V3.18 E9 (Entwurf): Referenz nach der eigenen Registereintragung
    fall(tmp, {"lauf_id": "L8", "github_run_id": "84", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "z",
               "ausgaben": {"vollarchiv_ergebnis_hash": "z"}, "e9": {"eingabe_hash_lauf": "vorher", "eingabe_hash_nach_eintragung": "nachher"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="84"))
    i = json.load(open(os.path.join(tmp, "index.json")))
    ok(i["letzter_eingabe_hash"] == "nachher" and i["letzter_gueltiger_lauf"] == "L8", "V3.18 E9: Referenz ist der Stand nach der Registereintragung")

with tempfile.TemporaryDirectory() as tmp:   # 9 V3.18 §6 (Entwurf): gescheiterter Montagstest entzieht den Nachweis
    fall(tmp, {"lauf_id": "L9", "github_run_id": "85", "stufen": {"suche": "übersprungen"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH, "lauf_id": "L0"}, "letzter_eingabe_hash": "g", "letzter_gueltiger_lauf": "L0"}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="85", STUFE_TESTS="success", STUFE_SIEGELTEST="failure", STUFE_SUCHE="skipped"))
    i = json.load(open(os.path.join(tmp, "index.json")))
    ok("pruefungen_bestanden" not in i and i["pruefungen_gescheitert"]["lauf_id"] == "L9", "§6: Nachweis entzogen")
    json.dump({"lauf_id": "L10", "github_run_id": "86", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "w",
               "ausgaben": {"vollarchiv_ergebnis_hash": "w"}, "e9": {"eingabe_hash_lauf": "g10"}},
              open(os.path.join(tmp, "suche", "laeufe", "L10.json"), "w"))
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="86"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L10.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "teilweise" and e["e38"]["pruefungen"]["status"] == "kein Nachweis für diesen Prüfstand" and i["letzter_gueltiger_lauf"] == "L0",
       "§6: Folgelauf ohne Nachweis ist TEIL und wird nicht Referenz")

with tempfile.TemporaryDirectory() as tmp:   # 10 V3.18 §6: ein beim Mischen zurückgekehrter älterer Nachweis gilt nicht
    fall(tmp, {"lauf_id": "L20261103T050000Z", "github_run_id": "87", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "v",
               "ausgaben": {"vollarchiv_ergebnis_hash": "v"}, "e9": {"eingabe_hash_lauf": "g11"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH, "lauf_id": "L20261026T050000Z"},
          "pruefungen_gescheitert": {"pruef_hash": PH, "lauf_id": "L20261102T050000Z"}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="87"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L20261103T050000Z.json")))
    ok(e["gesamt"] == "teilweise" and e["e38"]["pruefungen"]["status"] == "kein Nachweis für diesen Prüfstand",
       "§6: jüngeres Scheitern schlägt einen zurückgekehrten älteren Nachweis")

with tempfile.TemporaryDirectory() as tmp:   # 11 V3.18 §6: neuer Nachweis nach einem älteren Scheitern gilt
    fall(tmp, {"lauf_id": "L20261110T050000Z", "github_run_id": "88", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "u",
               "ausgaben": {"vollarchiv_ergebnis_hash": "u"}, "e9": {"eingabe_hash_lauf": "g12"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH, "lauf_id": "L20261109T050000Z"},
          "pruefungen_gescheitert": {"pruef_hash": PH, "lauf_id": "L20261102T050000Z"}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="88"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L20261110T050000Z.json")))
    ok(e["gesamt"] == "vollständig" and e["e38"]["pruefungen"]["status"] == "bestanden für identischen Prüfstand",
       "§6: neuerer Nachweis nach älterem Scheitern gilt")

# ---------------------------------------------------------------- Gutachten 23 (Fassung 2)
HIER = os.path.dirname(os.path.abspath(__file__))
with tempfile.TemporaryDirectory() as tmp:   # 12 M4: Tests und Rechenumgebung gehören zum Prüfstand
    import shutil
    for f in PRUEF_DATEIEN:
        if os.path.exists(os.path.join(HIER, f)):
            os.makedirs(os.path.dirname(os.path.join(tmp, f)) or tmp, exist_ok=True)
            shutil.copy(os.path.join(HIER, f), os.path.join(tmp, f))
    u = umgebung()
    ok(pruef_hash(tmp) == PH, "M4: Kopie des Prüfstands hat dieselbe Prüfsumme")
    h0 = pruef_hash(tmp, umg=u, mit_umgebung=True)
    ok(pruef_hash(tmp, umg=dict(u, numpy="9.9.9"), mit_umgebung=True) != h0
       and pruef_hash(tmp, umg=dict(u, NPY_DISABLE_CPU_FEATURES="TEST"), mit_umgebung=True) != h0
       and pruef_hash(tmp, umg=dict(u, tzdata="0000.0"), mit_umgebung=True) != h0,
       "M4 (mit §6): andere Rechenumgebung (Paket, CPU-Einstellung) ergibt einen anderen Prüfstand")
    ok(pruef_hash(tmp, umg=dict(u, ImageVersion="TEST"), mit_umgebung=True) == h0,
       "M4: Rechner-Abbild nur vermerkt, kein neuer Prüfstand bei der wöchentlichen Verteilung")
    ok(pruef_hash(tmp, umg=dict(u, numpy="9.9.9"), mit_umgebung=False) == pruef_hash(tmp, umg=u, mit_umgebung=False),
       "ohne §6: Prüfstand wie V3.17 nur aus den Dateien")
    h1 = pruef_hash(tmp, mit_umgebung=False)
    open(os.path.join(tmp, "test_discovery.py"), "a").write("\n# geändert\n")
    ok(pruef_hash(tmp, umg=u, mit_umgebung=True) != h0 and pruef_hash(tmp, mit_umgebung=False) != h1,
       "M4: geänderter Test ergibt einen anderen Prüfstand")

AUS = {"stand": {"nicht_eingefroren": [{"datei": "n__neu__x.csv", "grund": "Anführungszeichen"}]}}
PH6 = pruef_hash(HIER, mit_umgebung=True)   # Prüfstand mit §6 (PS_PAR6=1)

with tempfile.TemporaryDirectory() as tmp:   # 13 M4: Ausnahmepfad ohne Siegelnachweis -> TEIL, Meldung an den nächsten Lauf
    fall(tmp, {"lauf_id": "L13", "github_run_id": "89", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "a",
               "ausgaben": {"vollarchiv_ergebnis_hash": "a"}, "e9": dict(AUS, eingabe_hash_lauf="g13")},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH6, "lauf_id": "L12", "ausnahmen_abgedeckt": []}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="89", PS_PAR6="1"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L13.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "teilweise" and e["e38"]["pruefungen"]["ausnahmen_ohne_siegel"] == ["n__neu__x.csv"]
       and i["ausnahmen_ohne_siegel"]["dateien"] == ["n__neu__x.csv"] and "letzter_gueltiger_lauf" not in i,
       "M4: nicht eingefrorene Datei ohne Siegelnachweis -> TEIL, keine Referenz")
    r = subprocess.run([sys.executable, os.path.join(HIER, "lauf_status.py"), "--nachweis"], capture_output=True, text=True,
                       env=dict(os.environ, PS_LERNEN_DIR=tmp, GITHUB_OUTPUT=os.path.join(tmp, "out"), PS_PAR6="1"))
    ok(r.returncode == 0 and open(os.path.join(tmp, "out")).read().strip() == "gueltig=false",
       "Soll: nach einem Ausnahmepfad ohne Siegelnachweis laufen Tests und Siegeltest zuerst")

with tempfile.TemporaryDirectory() as tmp:   # 14 M4: Siegeltest dieses Laufs deckt die Datei ab -> vollständig, Meldung gelöscht
    fall(tmp, {"lauf_id": "L14", "github_run_id": "90", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "b",
               "ausgaben": {"vollarchiv_ergebnis_hash": "b"}, "e9": dict(AUS, eingabe_hash_lauf="g14")},
         {"laeufe": [], "ausnahmen_ohne_siegel": {"lauf_id": "L13", "dateien": ["n__neu__x.csv"]}}, {})
    json.dump({"ausnahmen_abgedeckt": ["n__neu__x.csv"], "bestanden": True}, open(os.path.join(tmp, "abd.json"), "w"))
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="90", STUFE_TESTS="success", STUFE_SIEGELTEST="success", PS_SIEGEL_ABDECKUNG=os.path.join(tmp, "abd.json"), PS_PAR6="1"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L14.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "vollständig" and i["pruefungen_bestanden"]["ausnahmen_abgedeckt"] == ["n__neu__x.csv"]
       and "ausnahmen_ohne_siegel" not in i, "M4: Siegelnachweis über den Stand deckt die Ausnahme ab")

with tempfile.TemporaryDirectory() as tmp:   # 15 Soll: Workflow-Schritt «Prüfnachweis»
    def nachweis_cli(idx):
        json.dump(idx, open(os.path.join(tmp, "index.json"), "w"))
        out = os.path.join(tmp, "out"); open(out, "w").close()
        r = subprocess.run([sys.executable, os.path.join(HIER, "lauf_status.py"), "--nachweis"], capture_output=True, text=True,
                           env=dict(os.environ, PS_LERNEN_DIR=tmp, GITHUB_OUTPUT=out, PS_PAR6="1"))
        return r.returncode, open(out).read().strip()
    from datetime import datetime, timedelta, timezone
    JETZT = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    ALT = (datetime.now(timezone.utc) - timedelta(days=8)).strftime("%Y-%m-%dT%H:%M:%SZ")
    ok(nachweis_cli({"pruefungen_bestanden": {"pruef_hash": PH6, "lauf_id": "L1", "zeit_utc": JETZT}}) == (0, "gueltig=true"),
       "Soll: gültiger Nachweis -> keine Tests nötig")
    ok(nachweis_cli({"pruefungen_bestanden": {"pruef_hash": PH6, "lauf_id": "L1", "zeit_utc": ALT}}) == (0, "gueltig=false")
       and nachweis_cli({"pruefungen_bestanden": {"pruef_hash": PH6, "lauf_id": "L1"}}) == (0, "gueltig=false"),
       "Soll: Nachweis älter als 7 Tage oder ohne Zeitpunkt -> Tests zuerst (unabhängig vom Montagslauf)")
    ok(nachweis_cli({"pruefungen_bestanden": {"pruef_hash": "anderer", "lauf_id": "L1"}}) == (0, "gueltig=false"), "Soll: anderer Prüfstand -> Tests zuerst")
    ok(nachweis_cli({"pruefungen_bestanden": {"pruef_hash": PH6, "lauf_id": "L1", "zeit_utc": JETZT},
                     "pruefungen_gescheitert": {"pruef_hash": PH6, "lauf_id": "L2", "zeit_utc": JETZT}}) == (0, "gueltig=false"), "Soll: entzogener Nachweis -> Tests zuerst")
    os.remove(os.path.join(tmp, "index.json"))
    out = os.path.join(tmp, "out"); open(out, "w").close()
    r = subprocess.run([sys.executable, os.path.join(HIER, "lauf_status.py"), "--nachweis"], capture_output=True, text=True,
                       env=dict(os.environ, PS_LERNEN_DIR=tmp, GITHUB_OUTPUT=out))
    ok(r.returncode == 0 and open(out).read().strip() == "gueltig=false", "Soll: ohne index.json -> Tests zuerst, kein Abbruch")

with tempfile.TemporaryDirectory() as tmp:   # 16 M4: Siegeltest nicht bestanden -> deckt nichts ab
    fall(tmp, {"lauf_id": "L16", "github_run_id": "91", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "c",
               "ausgaben": {"vollarchiv_ergebnis_hash": "c"}, "e9": dict(AUS, eingabe_hash_lauf="g16")}, {"laeufe": []}, {})
    json.dump({"ausnahmen_abgedeckt": ["n__neu__x.csv"], "bestanden": False}, open(os.path.join(tmp, "abd.json"), "w"))
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="91", STUFE_TESTS="success", STUFE_SIEGELTEST="success", PS_SIEGEL_ABDECKUNG=os.path.join(tmp, "abd.json"), PS_PAR6="1"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L16.json")))
    ok(e["gesamt"] == "teilweise" and e["e38"]["pruefungen"]["ausnahmen_ohne_siegel"] == ["n__neu__x.csv"],
       "M4: Abdeckung nur aus einem bestandenen Siegeltest")

with tempfile.TemporaryDirectory() as tmp:   # 17 Finalistenregel (Reto 15.10.2026): Prüfungen im selben Lauf
    fall(tmp, {"lauf_id": "L17", "github_run_id": "92", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "d",
               "ausgaben": {"vollarchiv_ergebnis_hash": "d"}, "e9": {"eingabe_hash_lauf": "g17"}}, {"laeufe": []}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="92", STUFE_TESTS="success", STUFE_SIEGELTEST="success"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L17.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["e38"]["finalist_zulaessig"] is True and i["pruefungen_bestanden"]["eingabe_hash"] == "g17",
       "Finalist: Prüfungen im selben Lauf genügen; Nachweis nennt die geprüfte Eingabe")
    json.dump({"lauf_id": "L18", "github_run_id": "93", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "f",
               "ausgaben": {"vollarchiv_ergebnis_hash": "f"}, "e9": {"eingabe_hash_lauf": "g18", "eingabe_hash_nach_eintragung": "g17"}},
              open(os.path.join(tmp, "suche", "laeufe", "L18.json"), "w"))
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="93"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L18.json")))
    ok(e["e38"]["importierbar"] is True and e["e38"]["finalist_zulaessig"] is False,
       "Finalist: andere tatsächliche Eingabe -> importierbar, aber kein Finalist (Vergleichsstand zählt nicht)")
    ok(e["e38"]["nachweis_bei_geaenderter_eingabe"].startswith("Ausnahme nach V3.18 §6" if os.environ.get("PS_PAR6") == "1" else "Vorbehalt"),
       "E38: Nachweis bei geänderter Eingabe ist ausgewiesen (mit §6 Ausnahme, ohne §6 Vorbehalt wie 15.10.2026)")
    json.dump({"lauf_id": "L19", "github_run_id": "94", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "h",
               "ausgaben": {"vollarchiv_ergebnis_hash": "h"}, "e9": {"eingabe_hash_lauf": "g17"}},
              open(os.path.join(tmp, "suche", "laeufe", "L19.json"), "w"))
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="94"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L19.json")))
    ok(e["e38"]["finalist_zulaessig"] is True, "Finalist: Nachweis mit identischer tatsächlicher Eingabe genügt")

with tempfile.TemporaryDirectory() as tmp:   # 18 Entzug: Zeitpunkt entscheidet, nicht die Lauf-ID (erneuter Versuch eines GitHub-Laufs)
    fall(tmp, {"lauf_id": "L20261103T050000Z", "github_run_id": "95", "stufen": {"suche": "vollständig"}, "ergebnis_hash": "k",
               "ausgaben": {"vollarchiv_ergebnis_hash": "k"}, "e9": {"eingabe_hash_lauf": "g20"}},
         {"laeufe": [], "pruefungen_bestanden": {"pruef_hash": PH, "lauf_id": "L20261102T050000Z", "zeit_utc": "2026-11-02T05:30:00Z"},
          "pruefungen_gescheitert": {"pruef_hash": PH, "lauf_id": "L20261101T050000Z", "zeit_utc": "2026-11-02T07:00:00Z"}}, {})
    lauf(tmp, dict(ALLES, GITHUB_RUN_ID="95"))
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L20261103T050000Z.json")))
    ok(e["gesamt"] == "teilweise", "Entzug: jüngeres Scheitern nach Zeitpunkt gilt, auch mit älterer Lauf-ID")

# Gutachten 23, M2: Entscheidungs-Prüfsumme (Positivliste in eingabe.py)
from eingabe import entscheidung_pruefsumme  # noqa: E402
Z = {"kandidaten": 5, "huerde_t": 4.4, "placebo_bestes_t_je_lauf_roh": [3.9, 4.1], "bausteine": [{"indikator": "x", "t": 4.8}],
     "p_lauf": 0.03, "kalibrierung": {"effekt_x1": 0.5}, "kandidaten_neu": 3, "kandidaten_kumuliert": 10, "staerkste_neue": [1],
     "huerde_bonferroni_bericht": 5.3, "reihen_bericht": {"abruffehler_mit_datei": ["a"]}, "dauer_min": 90, "umgebung": {"numpy": "2"}}
h_ = entscheidung_pruefsumme(Z)
ok(h_ == entscheidung_pruefsumme(dict(Z, kandidaten_neu=0, kandidaten_kumuliert=13, staerkste_neue=[], huerde_bonferroni_bericht=5.4,
                                       reihen_bericht={"abruffehler_mit_datei": ["b"]}, dauer_min=170, umgebung={"numpy": "3"})),
   "M2: Register, Zähler, Manifest-Berichte, Dauer und Umgebung ändern die Entscheidungs-Prüfsumme nicht")
ok(h_ != entscheidung_pruefsumme(dict(Z, placebo_bestes_t_je_lauf_roh=[3.9, 4.2])) and h_ != entscheidung_pruefsumme(dict(Z, bausteine=[]))
   and h_ != entscheidung_pruefsumme(dict(Z, kalibrierung={"effekt_x1": 0.6})),
   "M2: Placebo-Pfad, Kandidaten der Stufe D und Kalibrierung ändern sie")

print("alle Tests bestanden")
