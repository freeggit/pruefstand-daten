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

with tempfile.TemporaryDirectory() as tmp:   # 1 alles gelungen
    os.makedirs(os.path.join(tmp, "suche", "laeufe"))
    json.dump({"lauf_id": "L1", "github_run_id": "77", "stufen": {"suche": "vollständig", "analyse": "ausstehend", "familie_v": "ausstehend"}}, open(os.path.join(tmp, "suche", "laeufe", "L1.json"), "w"))
    json.dump({"lauf_id": "L1", "kandidaten": 5}, open(os.path.join(tmp, "suche", "letzter_lauf.json"), "w"))
    json.dump({"laeufe": [{"datei": "suche/laeufe/L1.json", "lauf_id": "L1"}]}, open(os.path.join(tmp, "index.json"), "w"))
    lauf(tmp, {"GITHUB_RUN_ID": "77", "STUFE_TESTS": "skipped", "STUFE_SIEGELTEST": "skipped", "STUFE_SUCHE": "success", "STUFE_ANALYSE": "success", "STUFE_FAMILIE_V": "success"})
    e = json.load(open(os.path.join(tmp, "suche", "laeufe", "L1.json"))); l = json.load(open(os.path.join(tmp, "suche", "letzter_lauf.json"))); i = json.load(open(os.path.join(tmp, "index.json")))
    ok(e["gesamt"] == "vollständig" and e["stufen"]["analyse"] == "vollständig" and e["stufen"]["tests"] == "übersprungen", "alles gelungen: gesamt vollständig")
    ok(l["gesamt"] == "vollständig" and l["kandidaten"] == 5, "letzter_lauf.json nachgeführt, Inhalt bleibt")
    ok(i["laeufe"] == [{"datei": "suche/laeufe/L1.json", "lauf_id": "L1", "gesamt": "vollständig"}], "index: kein Doppel, gesamt eingetragen")

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
print("alle Tests bestanden")
