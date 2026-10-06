"""Ergebnisse aus _lernen auf den Zweig claude/lernen einchecken (Suche, Vorregistrierung).

Aufruf in der Action:  python einchecken.py "Suchlauf"   bzw.   python einchecken.py "Vorregistrierung"

Warum ein eigenes Skript (30.9.2026, Lauf #18 verloren):
- `git fetch origin claude/lernen` aktualisiert origin/claude/lernen im Checkout der Action nicht
  (Fetch-Refspec nur für main). Der Rebase lief gegen den alten Stand, der Push wurde abgewiesen.
  Hier wird mit explizitem Ziel geholt: claude/lernen:refs/remotes/origin/claude/lernen.
- index.json wird von Suche, Lernrunde und Vorregistrierung geschrieben. Überschneiden sich die
  Änderungen, wird index.json dreiweg gemischt (Basis, Stand auf GitHub, eigener Stand) statt aufzugeben.
  Listen (suchlaeufe, lernberichte, vorreg) werden nach «datei» bzw. «charge» vereinigt; sonst gilt der
  eigene Wert, wo er von der Basis abweicht, und der Stand auf GitHub, wo nicht.
- Andere Dateien mit Konflikt: der eigene Stand gilt (jede Datei hat genau einen Schreiber), mit Meldung.
Nichts wird gelöscht oder stillschweigend verworfen; scheitert alles, endet das Skript mit Fehler 1.

Korrekturen 2.10.2026 (Astra-Befund 19, Reto: «Paket 1 wie vorgeschlagen»):
- Listenschlüssel: der erste NICHT leere Wert aus nr, charge, datei, datum (vorher galt «datei: null» der Läufe 1–4
  als gemeinsamer Schlüssel; Einträge konnten sich gegenseitig ersetzen).
- Einträge mit gleichem Schlüssel werden feldweise dreiweg gemischt. Ändern beide Seiten dasselbe Feld verschieden,
  bleibt der schon veröffentlichte Wert und der eigene wird in index["konflikte"] festgehalten (nichts geht verloren).
  Bei Feldern der obersten Ebene (Zustand des letzten Laufs) gilt wie bisher der eigene Wert; der ersetzte wird festgehalten.
- Andere Dateien mit Konflikt: der eigene Stand gilt weiterhin, der Stand von GitHub wird daneben als
  <pfad>.konflikt_<zeit> gesichert statt verworfen.
- Tests: python test_einchecken.py

V3.11 (E28, 4.10.2026, Reto: «ok, gerne freigeben»; Astra-Gutachten 4, Befunde N04 und N05):
- Ein veröffentlichtes Endurteil der Familie V darf sich nicht ändern. Vor jedem Push wird jede Datei vorreg/<charge>.json
  gegen den frisch geholten Stand geprüft (integritaet.endurteil_geaendert), auch ohne Textkonflikt. Bei einem Verstoss
  bleibt die veröffentlichte Fassung, die eigene wird als <pfad>.verworfen_<zeit> daneben gelegt, der Verstoss steht in
  index["konflikte"], der Rest des Laufs wird eingecheckt und das Skript endet mit Fehler 1 (sichtbar im Workflow).
- Listenschlüssel: leere Zeichenketten gelten wie fehlende Werte. Gleiche Kennung mit verschiedenem Inhalt auf der eigenen
  Seite ist ein Konflikt: beide Einträge bleiben, der Konflikt wird festgehalten. Bekommt ein Eintrag später erstmals eine
  Nummer, wird er über «datei» wiedererkannt statt verdoppelt.
- Das Konfliktjournal wird nicht mehr gekürzt.
"""
import json, os, subprocess, sys, time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import integritaet as it  # noqa: E402

ZWEIG = "claude/lernen"
REF = f"refs/remotes/origin/{ZWEIG}"
ROOT = os.path.dirname(os.path.abspath(__file__))
LERNEN = os.environ.get("PS_LERNEN_DIR", os.path.join(ROOT, "_lernen"))
PRAEFIX = sys.argv[1] if len(sys.argv) > 1 else "Lauf"


def git(*a, ok=False, text=True):
    r = subprocess.run(["git", "-C", LERNEN, *a], capture_output=True, text=text)
    if not ok and r.returncode != 0:
        raise RuntimeError(f"git {' '.join(a)}: {r.stderr.strip()[-500:]}")
    return r


KONFLIKTE = []


def schluessel(e):
    if isinstance(e, dict):
        for k in ("nr", "charge", "datei", "datum"):
            if e.get(k) is not None and e.get(k) != "":
                return (k, json.dumps(e[k], sort_keys=True))
    return ("wert", json.dumps(e, sort_keys=True, ensure_ascii=False))


def eintrag_mischen(b, t, m, wo):
    """Feldweise dreiweg: b Basis (oder None), t Stand auf GitHub, m eigener Stand."""
    if not (isinstance(t, dict) and isinstance(m, dict)):
        return m
    b = b if isinstance(b, dict) else {}
    out = dict(t)
    for k, v in m.items():
        if k in t and t[k] == v:
            continue
        if k in b and b[k] == v:
            continue                    # nicht von mir geändert: Stand auf GitHub gilt
        if k in t and (k not in b or t[k] != b[k]):
            # beide Seiten haben das Feld verschieden gesetzt: der veröffentlichte Wert bleibt, meiner wird festgehalten
            KONFLIKTE.append({"wo": wo, "feld": k, "github_bleibt": t[k], "eigen_verworfen": v})
            continue
        out[k] = v
    return out                          # Felder werden nie entfernt


def _datei(e):
    d = e.get("datei") if isinstance(e, dict) else None
    return d if d not in (None, "") else None


def liste_mischen(basis, theirs, mine, wo="liste"):
    b, m, doppelt = {}, {}, []
    for e in basis or []:
        b.setdefault(schluessel(e), e)
    for e in mine or []:
        k = schluessel(e)
        if k in m:
            if m[k] != e:               # gleiche Kennung, anderer Inhalt auf der eigenen Seite: Konflikt, beide bleiben
                doppelt.append(e)
                KONFLIKTE.append({"wo": f"{wo}[{k[0]}={k[1]}]", "feld": "(Eintrag)", "art": "gleiche Kennung, verschiedener Inhalt",
                                  "erster": m[k], "zweiter": e})
            continue                    # identische Doppel fallen zusammen
        m[k] = e
    # Wiedererkennen über «datei», wenn eine Seite erstmals eine Nummer vergibt (sonst entstünde ein Doppel)
    t_datei = {}
    for e in theirs or []:
        if _datei(e) is not None:
            t_datei.setdefault(_datei(e), schluessel(e))
    alias = {}
    for k, e in m.items():
        d = _datei(e)
        if d is not None and d in t_datei and t_datei[d] != k and t_datei[d] not in m:
            alias[t_datei[d]] = k       # Schlüssel auf GitHub -> mein Schlüssel für denselben Eintrag
    out, gesehen = [], set()
    for e in theirs or []:
        k = schluessel(e)
        if k in gesehen:
            out.append(e); continue     # doppelter Schlüssel auf GitHub: nichts verwerfen
        gesehen.add(k)
        km = alias.get(k, k)
        if km in m and m[km] != e:
            gesehen.add(km)
            out.append(eintrag_mischen(b.get(km, b.get(k)), e, m[km], f"{wo}[{k[0]}={k[1]}]"))
        else:
            out.append(e)               # gleich, oder bei mir nicht vorhanden: bleibt (nie still verwerfen)
    for k, e in m.items():
        if k not in gesehen:
            gesehen.add(k); out.append(e)   # nur bei mir neu
    return out + doppelt


def json_mischen(basis, theirs, mine):
    if not all(isinstance(x, dict) for x in (theirs, mine)):
        return mine
    basis = basis if isinstance(basis, dict) else {}
    out = dict(theirs)
    for k, v in mine.items():
        if k in basis and basis[k] == v:
            continue                    # nicht von mir geändert: Stand auf GitHub gilt
        t = theirs.get(k)
        if isinstance(v, list) and isinstance(t, list) and all(isinstance(e, dict) for e in v + t):
            out[k] = liste_mischen(basis.get(k), t, v, k)
        else:
            if k in theirs and t != v and t != basis.get(k):
                KONFLIKTE.append({"wo": "index", "feld": k, "github_ersetzt": t, "eigen_gilt": v})
            out[k] = v
    if KONFLIKTE:
        zeit = time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())
        alt = out.get("konflikte") if isinstance(out.get("konflikte"), list) else []
        out["konflikte"] = alt + [dict(x, zeit=zeit, lauf=PRAEFIX) for x in KONFLIKTE]   # V3.11: ungekürzt
        del KONFLIKTE[:]
    return out


def blob(stufe, pfad):
    r = git("show", f":{stufe}:{pfad}", ok=True)
    return r.stdout if r.returncode == 0 else None


def konflikte_loesen():
    dateien = [p for p in git("diff", "--name-only", "--diff-filter=U").stdout.split("\n") if p]
    if not dateien:
        return False
    for p in dateien:
        # im Rebase: Stufe 2 = Stand auf GitHub (upstream), Stufe 3 = eigener Commit
        if p.endswith("index.json"):
            b, t, m = (blob(s, p) for s in (1, 2, 3))
            gem = json_mischen(json.loads(b) if b else {}, json.loads(t) if t else {}, json.loads(m) if m else {})
            with open(os.path.join(LERNEN, p), "w", encoding="utf-8") as f:
                json.dump(gem, f, ensure_ascii=False, indent=1)
            print(f"Konflikt in {p}: dreiweg gemischt")
        else:
            t = git("show", f":2:{p}", ok=True, text=False)
            if t.returncode == 0:       # Stand von GitHub daneben sichern statt verwerfen
                sich = f"{p}.konflikt_{time.strftime('%Y%m%dT%H%M%SZ', time.gmtime())}"
                with open(os.path.join(LERNEN, sich), "wb") as f:
                    f.write(t.stdout)
                git("add", "--", sich)
                print(f"Konflikt in {p}: Stand von GitHub gesichert als {sich}")
            if git("checkout", "--theirs", "--", p, ok=True).returncode == 0:
                print(f"Konflikt in {p}: eigener Stand übernommen (einziger Schreiber)")
            else:                       # bei mir nicht vorhanden: Stand von GitHub bleibt, nichts wird gelöscht
                git("checkout", "--ours", "--", p)
                print(f"Konflikt in {p}: Stand von GitHub behalten")
        git("add", "--", p)
    return True


def endurteile_schuetzen():
    """V3.11 (E28): Ein veröffentlichtes Endurteil darf sich nicht ändern – auch ohne Textkonflikt. Vergleicht jede Datei
    vorreg/<charge>.json im eigenen Stand mit dem frisch geholten Stand. Bei Verstoss: veröffentlichte Fassung bleibt,
    eigene Fassung daneben als .verworfen_<zeit>, Eintrag in index["konflikte"]. Gibt die Zahl der Verstösse zurück."""
    r = git("ls-tree", "-r", "--name-only", REF, "vorreg", ok=True)
    if r.returncode != 0:
        return 0
    n = 0
    zeit = time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for p in [x for x in r.stdout.split("\n") if x.endswith(".json") and "/" in x and x.count("/") == 1]:
        t = git("show", f"{REF}:{p}", ok=True)
        if t.returncode != 0:
            continue
        lokal = os.path.join(LERNEN, p)
        try:
            ver = json.loads(t.stdout)
        except ValueError:
            continue
        try:
            eig = json.load(open(lokal, encoding="utf-8")) if os.path.exists(lokal) else {"hypothesen": []}
        except ValueError:
            eig = {"hypothesen": []}
        verst = it.endurteil_geaendert(ver, eig)
        if not verst:
            continue
        n += 1
        if os.path.exists(lokal):
            os.replace(lokal, f"{lokal}.verworfen_{zeit}")
        with open(lokal, "w", encoding="utf-8") as f:
            f.write(t.stdout)
        ip = os.path.join(LERNEN, "index.json")
        try:
            idx = json.load(open(ip, encoding="utf-8"))
        except (OSError, ValueError):
            idx = None
        if isinstance(idx, dict):
            alt = idx.get("konflikte") if isinstance(idx.get("konflikte"), list) else []
            idx["konflikte"] = alt + [{"wo": p, "art": "Endurteil geschützt: veröffentlichte Fassung bleibt", "verstoesse": verst[:20],
                                       "verstoesse_n": len(verst), "eigene_fassung": f"{p}.verworfen_{zeit}",
                                       "zeit": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lauf": PRAEFIX}]
            with open(ip, "w", encoding="utf-8") as f:
                json.dump(idx, f, ensure_ascii=False, indent=1)
        print(f"SCHUTZ {p}: {len(verst)} Abweichung(en) von einem veröffentlichten Endurteil; veröffentlichte Fassung bleibt, "
              f"eigene Fassung gesichert als {p}.verworfen_{zeit}")
    if n:
        git("add", "-A")
        if git("diff", "--cached", "--quiet", ok=True).returncode != 0:
            git("commit", "-q", "-m", f"{PRAEFIX}: Endurteil geschützt ({n} Datei(en)) {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())}")
    return n


def s_nummern_freimachen():
    """V3.12 (Schritt 2; Anlass: S0022 am 4.10.2026 von zwei Läufen vergeben). Die S-Nummer gilt erst mit dem Einchecken:
    Hat der eigene Lauf ein Dokument suche/S####.json neu angelegt, das auf GitHub inzwischen mit anderem Inhalt besteht,
    erhält der eigene Lauf die nächste freie Nummer. Umbenannt werden alle eigenen Dateien dieser Nummer; die Verweise in
    index.json, im Laufeintrag und in letzter_lauf.json werden nachgeführt und die Umnummerierung wird in
    index["berichtigungen"] festgehalten. Gibt die Liste (alt, neu) zurück."""
    import re
    basis = git("merge-base", "HEAD", REF, ok=True).stdout.strip()
    if not basis:
        return []
    eigene = [x for x in git("diff", "--name-only", "--diff-filter=A", basis, "HEAD").stdout.split("\n") if x]
    fern = [x for x in git("ls-tree", "-r", "--name-only", REF, "suche", ok=True).stdout.split("\n") if x]
    belegt = {int(m.group(1)) for x in fern + eigene for m in [re.match(r"suche/S(\d{4})[._]", x)] if m}
    try:
        belegt |= {int(e["nr"]) for e in json.loads(git("show", f"{REF}:index.json").stdout).get("suchlaeufe", []) if isinstance(e.get("nr"), int)}
    except (RuntimeError, ValueError):
        pass
    wechsel = []
    for x in sorted(eigene):
        m = re.fullmatch(r"suche/S(\d{4})\.json", x)
        if not m or x not in fern:
            continue
        if git("rev-parse", f"HEAD:{x}").stdout.strip() == git("rev-parse", f"{REF}:{x}").stdout.strip():
            continue                    # gleicher Inhalt: kein Zusammenstoss
        alt = int(m.group(1)); neu = max(belegt) + 1; belegt.add(neu)
        a, n = f"S{alt:04d}", f"S{neu:04d}"
        for d in [y for y in eigene if re.match(rf"suche/{a}[._]", y)]:
            git("mv", d, d.replace(f"suche/{a}", f"suche/{n}", 1))
        text = [f"suche/{n}.json", f"suche/{n}_analyse.json", "suche/letzter_lauf.json"] + [y for y in eigene if y.startswith("suche/laeufe/")]
        for d in text:
            pf = os.path.join(LERNEN, d)
            if os.path.exists(pf):
                t = open(pf, encoding="utf-8").read()
                if a in t:
                    open(pf, "w", encoding="utf-8").write(t.replace(a, n))
        pf = os.path.join(LERNEN, f"suche/{n}.json")
        try:
            sd = json.load(open(pf, encoding="utf-8"))
            if sd.get("nr") == alt:
                sd["nr"] = neu; sd["sort"] = neu; sd["nr_berichtigt"] = {"alt": alt, "grund": "Nummer war beim Einchecken schon vergeben"}
                json.dump(sd, open(pf, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        except (OSError, ValueError):
            pass
        ip = os.path.join(LERNEN, "index.json")
        try:
            idx = json.load(open(ip, encoding="utf-8"))
        except (OSError, ValueError):
            idx = None
        if isinstance(idx, dict):
            for e in idx.get("suchlaeufe", []):
                if e.get("datei") == f"suche/{a}.json" and e.get("nr") == alt:
                    e["nr"] = neu; e["datei"] = f"suche/{n}.json"
            for e in idx.get("laeufe", []):
                if isinstance(e.get("s_dokument"), str) and e.get("datei") in eigene:
                    e["s_dokument"] = e["s_dokument"].replace(a, n)
            if isinstance(idx.get("letztes_vollarchiv"), str) and f"suche/{a}_alle.csv.gz" in eigene:
                idx["letztes_vollarchiv"] = idx["letztes_vollarchiv"].replace(a, n)
            idx.setdefault("berichtigungen", []).append({"wo": "S-Nummer", "vorher": a, "jetzt": n, "grund": "Nummer war beim Einchecken auf GitHub schon mit anderem Inhalt vergeben",
                                                          "zeit": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "lauf": PRAEFIX})
            json.dump(idx, open(ip, "w", encoding="utf-8"), ensure_ascii=False, indent=1)
        wechsel.append((a, n))
        print(f"S-Nummer: {a} ist auf GitHub schon vergeben; eigener Lauf erhält {n}")
    if wechsel:
        # Ein einziger eigener Commit mit den neuen Namen: sonst träfe der ursprüngliche Commit im Rebase noch auf die
        # vergebene Nummer und die Datei des anderen Laufs würde ersetzt.
        git("add", "-A")
        git("reset", "-q", "--soft", basis)
        git("commit", "-q", "-m", f"{PRAEFIX} {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())} (GitHub Action; S-Nummer beim Einchecken: "
            f"{', '.join(f'{a} -> {n}' for a, n in wechsel)})")
    return wechsel


def main():
    git("config", "user.name", "pruefstand-bot")
    git("config", "user.email", "pruefstand-bot@users.noreply.github.com")
    git("add", "-A")
    if git("diff", "--cached", "--quiet", ok=True).returncode == 0:
        print("keine Änderung"); return 0
    git("commit", "-q", "-m", f"{PRAEFIX} {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())} (GitHub Action)")
    verstoesse = 0
    for versuch in range(1, 6):
        try:
            if git("ls-remote", "--exit-code", "--heads", "origin", ZWEIG, ok=True).returncode == 0:
                git("fetch", "-q", "origin", f"+{ZWEIG}:{REF}")
                s_nummern_freimachen()
                r = git("rebase", "-q", REF, ok=True)
                while r.returncode != 0:
                    if not konflikte_loesen():
                        git("rebase", "--abort", ok=True)
                        raise RuntimeError(f"Rebase gescheitert ohne lösbaren Konflikt: {r.stderr.strip()[-300:]}")
                    r = subprocess.run(["git", "-C", LERNEN, "-c", "core.editor=true", "rebase", "--continue"],
                                       capture_output=True, text=True)
                verstoesse += endurteile_schuetzen()
            r = git("push", "-q", "origin", f"HEAD:{ZWEIG}", ok=True)
            if r.returncode == 0:
                print(f"eingecheckt auf {ZWEIG}: {git('rev-parse', '--short', 'HEAD').stdout.strip()} (Versuch {versuch})")
                if verstoesse:
                    print(f"FEHLER: {verstoesse} Versuch(e), ein veröffentlichtes Endurteil zu ändern; die veröffentlichte Fassung blieb."); return 1
                return 0
            print(f"Versuch {versuch}: Push abgewiesen: {r.stderr.strip()[-300:]}")
        except RuntimeError as e:
            print(f"Versuch {versuch}: {e}")
        time.sleep(15 * versuch)
    print("Einchecken gescheitert"); return 1


if __name__ == "__main__":
    sys.exit(main())
