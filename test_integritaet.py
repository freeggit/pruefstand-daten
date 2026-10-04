"""Regressionstests zu V3.11, E28 (Astra-Gutachten 4, Befunde N02 bis N05). Aufruf: python test_integritaet.py
Ohne Netz und ohne Marktdaten. Der letzte Teil spielt in einem Wegwerf-Repo durch, dass ein veralteter Schreiber ein
veröffentlichtes Endurteil nicht mehr ersetzen kann – mit und ohne Textkonflikt."""
import copy, json, os, subprocess, sys, tempfile

sys.argv = [sys.argv[0], "Test"]
import einchecken as e
import integritaet as it


def ok(bed, name):
    assert bed, name
    print("ok ", name)


def wirft(f, name):
    try:
        f()
    except it.IntegritaetsFehler as x:
        print("ok ", name, "–", str(x)[:70]); return
    raise AssertionError(name + ": kein Fehler")


H = lambda i, ind="a": {"id": f"V-{i}", "indikator": f"{ind}{i}", "art": "hoch", "ziel": "xlk", "h": 20}
ch5 = {"charge": "c", "hypothesen": [H(i) for i in range(1, 6)]}

# 1 N02: eine offene Fünfercharge darf nicht auf zwei Hypothesen verkleinert werden
sha = it.familie_pruefen(ch5, None, 10)
alt = {"registrierung_sha": sha, "familie_n": 5, "hypothesen": []}
ch2 = {"charge": "c", "hypothesen": ch5["hypothesen"][:2]}
wirft(lambda: it.familie_pruefen(ch2, alt, 10), "N02 verkleinerte Familie wird abgewiesen")
ok(it.familie_pruefen(copy.deepcopy(ch5), alt, 10) == sha, "N02 unveränderte Registrierung wird angenommen")
ch_ziel = copy.deepcopy(ch5); ch_ziel["hypothesen"][0]["ziel"] = "xle"
wirft(lambda: it.familie_pruefen(ch_ziel, alt, 10), "N02 geändertes Ziel wird abgewiesen")
ch_reihe = copy.deepcopy(ch5); ch_reihe["hypothesen"].reverse()
wirft(lambda: it.familie_pruefen(ch_reihe, alt, 10), "N02 geänderte Reihenfolge wird abgewiesen")

# 2 N02: mehr als zehn Einträge sind eine ungültige Charge (kein stilles Abschneiden)
wirft(lambda: it.familie_pruefen({"charge": "c", "hypothesen": [H(i) for i in range(1, 12)]}, None, 10), "N02 elf Hypothesen: ungültig")
wirft(lambda: it.familie_pruefen({"charge": "c", "hypothesen": [H(1), H(1)]}, None, 10), "N02 doppelte id: ungültig")

# 3 N02: Altbestand ohne Prüfsumme – Schlüssel und Familiengrösse müssen trotzdem stimmen
alt_ohne = {"hypothesen": [{"schluessel": f"a{i}|hoch|xlk|20"} for i in range(1, 6)]}
ok(bool(it.familie_pruefen(ch5, alt_ohne, 10)), "N02 Altbestand: gleiche Schlüssel werden angenommen")
wirft(lambda: it.familie_pruefen(ch2, alt_ohne, 10), "N02 Altbestand: verkleinerte Familie wird abgewiesen")

# 4 N03: Astras Fall p = 100/9999. Gerundet 0.0100 ergäbe Holm 0.0500 (bestanden); aus Zähler und Nenner bleibt es 0.050005
z = {"status": "bewertet", "p_f5": 0.01, "p_f5_zaehler": 100, "p_f5_nenner": 9999}
ok(5 * it.p_roh(z) > 0.05, "N03 Entscheid aus Zähler und Nenner: nicht bestanden")
ok(5 * float(z["p_f5"]) <= 0.05, "N03 Gegenprobe: der gerundete Wert hätte bestanden")
ok(it.p_roh({"status": "bewertet", "p_f5": 0.2402}) == 0.2402, "N03 Altbestand ohne Zähler: gespeicherter Wert")
ok(it.p_roh({"status": "wartet"}) == 1.0, "N03 nicht bewertet: p = 1")
ok(it.wert_roh({"mu": 0.88, "roh": {"mu": 0.87996}}, "mu") == 0.87996, "N03 Entscheidgrösse ungerundet aus roh")

# 5 N05: leere Schlüssel, doppelte Nummer, später vergebene Nummer
aus = e.liste_mischen([], [], [{"nr": "", "datei": "a"}, {"nr": "", "datei": "b"}])
ok([x["datei"] for x in aus] == ["a", "b"], "N05 leere Nummer: beide Einträge bleiben")
del e.KONFLIKTE[:]
aus = e.liste_mischen([], [], [{"nr": 1, "value": "first"}, {"nr": 1, "value": "second"}])
ok(len(aus) == 2 and len(e.KONFLIKTE) == 1, "N05 gleiche Nummer, anderer Inhalt: beide bleiben, Konflikt festgehalten")
del e.KONFLIKTE[:]
aus = e.liste_mischen([], [], [{"nr": 1, "value": "x"}, {"nr": 1, "value": "x"}])
ok(aus == [{"nr": 1, "value": "x"}] and not e.KONFLIKTE, "N05 identisches Doppel fällt zusammen")
aus = e.liste_mischen([{"datei": "a"}], [{"datei": "a"}], [{"nr": 1, "datei": "a"}])
ok(aus == [{"datei": "a", "nr": 1}], "N05 später vergebene Nummer: ein Eintrag, kein Doppel")
aus = e.liste_mischen([{"datei": "a"}], [{"nr": 1, "datei": "a"}], [{"datei": "a", "in_db": True}])
ok(aus == [{"nr": 1, "datei": "a", "in_db": True}], "N05 Nummer von GitHub, Feld von mir: ein Eintrag")
del e.KONFLIKTE[:]
viele = [{"wo": "x", "feld": str(i)} for i in range(250)]
e.KONFLIKTE.extend(viele)
aus = e.json_mischen({}, {"a": 1}, {"a": 1})
ok(len(aus["konflikte"]) == 250, "N05 Konfliktjournal ungekürzt (250 Einträge)")

# 6 N04: Vergleich zweier Fassungen
fertig = {"registrierung_sha": "s", "familie_n": 2, "charge_vollstaendig": True, "hypothesen": [
    {"schluessel": "k1", "status": "bewertet", "p_f5": 0.2, "p_f5_zaehler": 2001, "p_f5_nenner": 10001, "t": 1.0, "code_hash": "neu", "p_holm": 0.4},
    {"schluessel": "k2", "status": "bewertet", "p_f5": 0.9, "p_f5_zaehler": 9001, "p_f5_nenner": 10001, "t": 0.1, "code_hash": "neu", "p_holm": 0.9}]}
ok(it.endurteil_geaendert(fertig, copy.deepcopy(fertig)) == [], "N04 gleiche Fassung: kein Verstoss")
holm_neu = copy.deepcopy(fertig); holm_neu["hypothesen"][0]["p_holm"] = 0.3
ok(it.endurteil_geaendert(fertig, holm_neu) == [], "N04 nur p_holm anders: erlaubt (Holm über die Familie)")
veraltet = copy.deepcopy(fertig); veraltet["hypothesen"][0].update({"p_f5": 0.21, "p_f5_zaehler": None, "p_f5_nenner": None, "code_hash": None})
ok({v["feld"] for v in it.endurteil_geaendert(fertig, veraltet)} == {"p_f5", "p_f5_zaehler", "p_f5_nenner", "code_hash"}, "N04 veraltete Fassung: Verstösse erkannt")
offen = copy.deepcopy(fertig); offen["hypothesen"][1] = {"schluessel": "k2", "status": "wartet"}
ok(it.endurteil_geaendert(offen, fertig) == [], "N04 wartende Zeile darf bewertet werden")
ok(len(it.endurteil_geaendert(fertig, offen)) >= 1, "N04 bewertete Zeile darf nicht wieder warten")

# 7 N04 im Wegwerf-Repo: (a) Textkonflikt, (b) kein Textkonflikt – das veröffentlichte Endurteil bleibt in beiden Fällen
def g(d, *a):
    r = subprocess.run(["git", "-C", d, *a], capture_output=True, text=True)
    assert r.returncode == 0, r.stderr
    return r.stdout


def spiel(mit_konflikt):
    with tempfile.TemporaryDirectory() as tmp:
        fern, a, b = (os.path.join(tmp, x) for x in ("fern.git", "a", "b"))
        subprocess.run(["git", "init", "-q", "--bare", fern], check=True)
        for d in (a, b):
            subprocess.run(["git", "init", "-q", d], check=True)
            g(d, "config", "user.name", "t"); g(d, "config", "user.email", "t@t"); g(d, "remote", "add", "origin", fern)

        def schreib(d, v, idx):
            os.makedirs(os.path.join(d, "vorreg"), exist_ok=True)
            json.dump(v, open(os.path.join(d, "vorreg", "c.json"), "w"), indent=1)
            json.dump(idx, open(os.path.join(d, "index.json"), "w"), indent=1)
        idx0 = {"suchlaeufe": [{"nr": 1, "datei": "S1"}], "vorreg": [{"charge": "c", "datei": "vorreg/c.json", "vollstaendig": False}]}
        if mit_konflikt:
            schreib(a, offen, idx0)                       # Basis: Charge offen
            g(a, "add", "-A"); g(a, "commit", "-qm", "basis"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
            g(b, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen"); g(b, "checkout", "-q", "-b", "arbeit", "origin/claude/lernen")
            schreib(a, fertig, idx0)                      # neuer Code schliesst die Charge ab und veröffentlicht
            g(a, "add", "-A"); g(a, "commit", "-qm", "neu"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
            schreib(b, veraltet, dict(idx0, suchlaeufe=idx0["suchlaeufe"] + [{"nr": 2, "datei": "S2"}]))   # veralteter Schreiber
        else:
            schreib(a, fertig, idx0)                      # Basis: Charge schon abgeschlossen und veröffentlicht
            g(a, "add", "-A"); g(a, "commit", "-qm", "basis"); g(a, "push", "-q", "origin", "HEAD:claude/lernen")
            g(b, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen"); g(b, "checkout", "-q", "-b", "arbeit", "origin/claude/lernen")
            schreib(b, veraltet, dict(idx0, suchlaeufe=idx0["suchlaeufe"] + [{"nr": 2, "datei": "S2"}]))   # ändert das Endurteil ohne Konflikt
        e.LERNEN = b
        code = e.main()
        g(a, "fetch", "-q", "origin", "+claude/lernen:refs/remotes/origin/claude/lernen")
        kanon = json.loads(g(a, "show", "origin/claude/lernen:vorreg/c.json"))
        idx = json.loads(g(a, "show", "origin/claude/lernen:index.json"))
        dateien = g(a, "ls-tree", "-r", "--name-only", "origin/claude/lernen").split()
        return code, kanon, idx, dateien


for mk, name in ((True, "mit Textkonflikt"), (False, "ohne Textkonflikt")):
    code, kanon, idx, dateien = spiel(mk)
    ok(kanon["hypothesen"] == fertig["hypothesen"], f"N04 {name}: veröffentlichtes Endurteil bleibt")
    ok(code == 1, f"N04 {name}: Lauf endet mit Fehler 1 (sichtbar)")
    ok(any(x.startswith("vorreg/c.json.verworfen_") for x in dateien), f"N04 {name}: eigene Fassung daneben gesichert")
    ok([x["nr"] for x in idx["suchlaeufe"]] == [1, 2], f"N04 {name}: der übrige Lauf ist eingecheckt")
    ok(any(k.get("art", "").startswith("Endurteil geschützt") for k in idx.get("konflikte", [])), f"N04 {name}: Verstoss im Konfliktjournal")
print("alle Tests bestanden")
