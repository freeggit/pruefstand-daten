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
from lauf_status import pruef_hash  # noqa: E402
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
    ok(e["gesamt"] == "vollständig" and i["pruefungen_bestanden"] == {"pruef_hash": PH, "lauf_id": "L6"}, "E38: bestandene Prüfungen werden Nachweis")

with tempfile.TemporaryDirectory() as tmp:   # 7 V3.17 E9: keine Neuberechnung ist weder Fehler noch Ergebnis
    fall(tmp, {"lauf_id": "L7", "github_run_id": "83", "stufen": {"suche": "keine Neuberechnung"}},
         {"laeufe": [], "letzter_eingabe_hash": "g", "letzter_gueltiger_lauf": "L6"}, {})
    lauf(tmp, {"GITHUB_RUN_ID": "83", "STUFE_TESTS": "skipped", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "skipped", "STUFE_FAMILIE_V": "skipped"})
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L7.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "keine Neuberechnung" and e["stufen"]["suche"] == "keine Neuberechnung" and not e["e38"]["importierbar"], "E9: Status keine Neuberechnung")
    ok(i["letzter_gueltiger_lauf"] == "L6" and i["letzter_eingabe_hash"] == "g", "E9: Referenz bleibt beim letzten gültigen Lauf")

print("alle Tests bestanden")
