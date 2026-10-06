"""Regressionstests für einchecken.py (Astra-Befund 19, 2.10.2026). Aufruf: python test_einchecken.py
Prüft das Mischen ohne Netz; der zweite Teil spielt einen echten Rebase-Konflikt in einem Wegwerf-Repo durch."""
import json, os, subprocess, sys, tempfile

sys.argv = [sys.argv[0], "Test"]
import einchecken as e

def gleich(a, b, name):
    assert a == b, f"{name}: {json.dumps(a, ensure_ascii=False)} != {json.dumps(b, ensure_ascii=False)}"
    print("ok ", name)

# 1 Schlüssel: «datei: null» darf nie Schlüssel sein
gleich(e.schluessel({"nr": 1, "datei": None}), ("nr", "1"), "Schlüssel nr vor datei null")
gleich(e.schluessel({"datei": None, "datum": "2026-09-28"}), ("datum", '"2026-09-28"'), "Schlüssel datum, wenn datei null")
assert e.schluessel({"nr": 1, "datei": None}) != e.schluessel({"nr": 2, "datei": None}); print("ok  Läufe 1 und 2 verschieden")

# 2 Astras Fall: Läufe 1–4 mit datei null, beide Seiten hängen an – alle bleiben
basis = [{"nr": i, "datei": None} for i in (1, 2, 3, 4)] + [{"nr": 5, "datei": "suche/S0005.json"}]
theirs = basis + [{"nr": 6, "datei": "suche/S0006.json"}]
mine = basis + [{"nr": 7, "datei": "suche/S0007.json"}]
aus = e.liste_mischen(basis, theirs, mine)
gleich([x["nr"] for x in aus], [1, 2, 3, 4, 5, 6, 7], "Läufe 1–4 bleiben, 6 und 7 kommen dazu")

# 3 feldweise: GitHub setzt in_db, ich setze analyse – beides bleibt
b = [{"nr": 5, "datei": "a", "in_db": False}]
t = [{"nr": 5, "datei": "a", "in_db": True}]
m = [{"nr": 5, "datei": "a", "in_db": False, "analyse": "x"}]
gleich(e.liste_mischen(b, t, m), [{"nr": 5, "datei": "a", "in_db": True, "analyse": "x"}], "feldweise gemischt")
assert not e.KONFLIKTE; print("ok  kein Konflikt gemeldet")

# 4 echter Feldkonflikt: veröffentlichter Wert bleibt, eigener wird festgehalten
b = {"vorreg": [{"charge": "c", "fund": False}], "x": 1}
t = {"vorreg": [{"charge": "c", "fund": False, "v_bausteine": 1}], "x": 1}
m = {"vorreg": [{"charge": "c", "fund": False, "v_bausteine": 0}], "x": 1}
aus = e.json_mischen(b, t, m)
gleich(aus["vorreg"], [{"charge": "c", "fund": False, "v_bausteine": 1}], "Feldkonflikt: GitHub bleibt")
assert aus["konflikte"][0]["eigen_verworfen"] == 0 and aus["konflikte"][0]["feld"] == "v_bausteine"; print("ok  Konflikt festgehalten")
assert not e.KONFLIKTE

# 5 oberste Ebene: mein geändertes Feld gilt, unverändertes nimmt GitHub
aus = e.json_mischen({"a": 1, "b": 1}, {"a": 2, "b": 1}, {"a": 1, "b": 3})
gleich(aus, {"a": 2, "b": 3}, "oberste Ebene dreiweg")

# 6 Listen ohne datei/charge (nur nr) werden jetzt auch vereinigt; reine Wertlisten: eigener Wert
aus = e.json_mischen({"l": [{"nr": 1}]}, {"l": [{"nr": 1}, {"nr": 2}]}, {"l": [{"nr": 1}, {"nr": 3}]})
gleich(aus["l"], [{"nr": 1}, {"nr": 2}, {"nr": 3}], "Liste nur mit nr vereinigt")
aus = e.json_mischen({"r": ["a"]}, {"r": ["a"]}, {"r": ["a", "b"]})
gleich(aus["r"], ["a", "b"], "Wertliste: eigener Stand")

# 7 nichts verschwindet: Eintrag nur auf GitHub bleibt, auch wenn er bei mir fehlt
gleich(e.liste_mischen([{"nr": 1}], [{"nr": 1}, {"nr": 9}], [{"nr": 1}]), [{"nr": 1}, {"nr": 9}], "fremder Eintrag bleibt")

# 8 Rebase im Wegwerf-Repo: index.json und eine weitere Datei im Konflikt
def g(d, *a):
    r = subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout
with tempfile.TemporaryDirectory() as tmp:
    fern, a, bdir = (os.path.join(tmp, x) for x in ("fern.git", "a", "b"))
    subprocess.run(["git", "init", "-q", "--bare", fern], check=True)
    for d in (a, bdir):
        subprocess.run(["git", "init", "-q", d], check=True)
        g(d, "config", "user.name", "t"); g(d, "config", "user.email", "t@t"); g(d, "remote", "add", "origin", fern)
    def schreib(d, idx, datei=None):
        json.dump(idx, open(os.path.join(d, "index.json"), "w"), indent=1)
        if datei is not None:
            open(os.path.join(d, "bericht.txt"), "w").write(datei)
    schreib(a, {"suchlaeufe": [{"nr": i, "datei": None} for i in (1, 2, 3, 4)]}, "basis\n")
    g(a, "add", "-A"); g(a, "commit", "-qm", "basis"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
    g(bdir, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen"); g(bdir, "checkout", "-q", "-b", "arbeit", "origin/claude/lernen")
    schreib(a, {"suchlaeufe": [{"nr": i, "datei": None} for i in (1, 2, 3, 4)] + [{"nr": 5, "datei": "S5"}]}, "github\n")
    g(a, "add", "-A"); g(a, "commit", "-qm", "anderer Schreiber"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
    schreib(bdir, {"suchlaeufe": [{"nr": i, "datei": None} for i in (1, 2, 3, 4)] + [{"nr": 6, "datei": "S6"}]}, "eigen\n")
    e.LERNEN = bdir
    assert e.main() == 0
    g(a, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen")
    idx = json.loads(g(a, "show", "origin/claude/lernen:index.json"))
    gleich([x["nr"] for x in idx["suchlaeufe"]], [1, 2, 3, 4, 5, 6], "Rebase: index.json gemischt und gepusht")
    dateien = g(a, "ls-tree", "--name-only", "origin/claude/lernen").split()
    sich = [x for x in dateien if x.startswith("bericht.txt.konflikt_")]
    assert len(sich) == 1 and g(a, "show", f"origin/claude/lernen:{sich[0]}") == "github\n"
    assert g(a, "show", "origin/claude/lernen:bericht.txt") == "eigen\n"
    print("ok  Rebase: andere Datei – eigener Stand gilt, GitHub-Stand gesichert als", sich[0])
# S-Nummer beim Einchecken (V3.12, Schritt 2): zwei Läufe vergeben dieselbe Nummer mit verschiedenem Inhalt
with tempfile.TemporaryDirectory() as tmp:
    fern, a, bdir = (os.path.join(tmp, x) for x in ("fern.git", "a", "b"))
    def g(d, *args):
        r = subprocess.run(["git", "-C", d, *args], capture_output=True, text=True)
        assert r.returncode == 0, r.stderr
        return r.stdout
    subprocess.run(["git", "init", "-q", "--bare", fern], check=True)
    for d in (a, bdir):
        subprocess.run(["git", "init", "-q", d], check=True)
        g(d, "config", "user.name", "t"); g(d, "config", "user.email", "t@t"); g(d, "remote", "add", "origin", fern)
    def lauf(d, nr, kandidaten, lauf_id):
        os.makedirs(os.path.join(d, "suche", "laeufe"), exist_ok=True)
        ip = os.path.join(d, "index.json")
        idx = json.load(open(ip)) if os.path.exists(ip) else {"suchlaeufe": [], "laeufe": []}
        n = f"S{nr:04d}"
        json.dump({"nr": nr, "sort": nr, "kandidaten": kandidaten, "lauf_id": lauf_id}, open(os.path.join(d, "suche", f"{n}.json"), "w"))
        open(os.path.join(d, "suche", f"{n}_log.txt"), "w").write(f"log {lauf_id}\n")
        open(os.path.join(d, "suche", f"{n}_alle.csv.gz"), "w").write(f"archiv {lauf_id}\n")
        json.dump({"lauf_id": lauf_id, "ausgaben": {"s_dokument": f"suche/{n}.json", "vollarchiv": f"suche/{n}_alle.csv.gz"}},
                  open(os.path.join(d, "suche", "laeufe", f"{lauf_id}.json"), "w"))
        json.dump({"lauf_id": lauf_id, "laufeintrag": f"suche/laeufe/{lauf_id}.json"}, open(os.path.join(d, "suche", "letzter_lauf.json"), "w"))
        idx["suchlaeufe"].append({"nr": nr, "datei": f"suche/{n}.json", "kandidaten": kandidaten, "in_db": False})
        idx["laeufe"].append({"datei": f"suche/laeufe/{lauf_id}.json", "lauf_id": lauf_id, "s_dokument": f"suche/{n}.json"})
        idx["letztes_vollarchiv"] = f"suche/{n}_alle.csv.gz"
        json.dump(idx, open(ip, "w"), indent=1)
    lauf(a, 21, 100, "L1")
    g(a, "add", "-A"); g(a, "commit", "-qm", "basis"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
    g(bdir, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen"); g(bdir, "checkout", "-q", "-b", "arbeit", "origin/claude/lernen")
    lauf(a, 22, 357302, "L2")
    g(a, "add", "-A"); g(a, "commit", "-qm", "anderer Lauf"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
    lauf(bdir, 22, 351452, "L3")
    e.LERNEN = bdir
    assert e.main() == 0
    g(a, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen")
    R = "origin/claude/lernen"
    idx = json.loads(g(a, "show", f"{R}:index.json"))
    gleich([(x["nr"], x["kandidaten"]) for x in idx["suchlaeufe"]], [(21, 100), (22, 357302), (23, 351452)], "S-Nummer: zweiter Lauf erhält 23, beide Einträge bleiben")
    gleich(json.loads(g(a, "show", f"{R}:suche/S0022.json"))["kandidaten"], 357302, "S-Nummer: S0022 bleibt beim ersten Lauf")
    s23 = json.loads(g(a, "show", f"{R}:suche/S0023.json"))
    gleich((s23["nr"], s23["kandidaten"], s23["nr_berichtigt"]["alt"]), (23, 351452, 22), "S-Nummer: S0023 gehört dem zweiten Lauf, Berichtigung vermerkt")
    gleich(g(a, "show", f"{R}:suche/S0023_alle.csv.gz"), "archiv L3\n", "S-Nummer: Vollarchiv mit umbenannt")
    gleich(g(a, "show", f"{R}:suche/S0022_alle.csv.gz"), "archiv L2\n", "S-Nummer: Vollarchiv des ersten Laufs unberührt")
    gleich(json.loads(g(a, "show", f"{R}:suche/laeufe/L3.json"))["ausgaben"], {"s_dokument": "suche/S0023.json", "vollarchiv": "suche/S0023_alle.csv.gz"}, "S-Nummer: Laufeintrag nachgeführt")
    gleich([x["s_dokument"] for x in idx["laeufe"]], ["suche/S0021.json", "suche/S0022.json", "suche/S0023.json"], "S-Nummer: Verweise der Läufe stimmen")
    gleich(idx["letztes_vollarchiv"], "suche/S0023_alle.csv.gz", "S-Nummer: letztes Vollarchiv nachgeführt")
    assert any(b.get("vorher") == "S0022" and b.get("jetzt") == "S0023" for b in idx["berichtigungen"]); print("ok  S-Nummer: Berichtigung im Index festgehalten")
    assert not [x for x in g(a, "ls-tree", "-r", "--name-only", R).split() if ".konflikt_" in x and "/S00" in x]; print("ok  S-Nummer: keine Konfliktkopie eines S-Dokuments nötig")
print("alle Tests bestanden")
