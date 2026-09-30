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
"""
import json, os, subprocess, sys, time

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


def schluessel(e):
    if isinstance(e, dict):
        for k in ("datei", "charge", "nr", "datum"):
            if k in e:
                return (k, json.dumps(e[k]))
    return ("wert", json.dumps(e, sort_keys=True))


def liste_mischen(basis, theirs, mine):
    b = {schluessel(e): e for e in (basis or [])}
    m = {schluessel(e): e for e in (mine or [])}
    out, gesehen = [], set()
    for e in theirs or []:
        k = schluessel(e); gesehen.add(k)
        if k in m and m[k] != b.get(k):
            out.append(m[k])            # von mir geändert oder neu
        elif k in b and k not in m:
            out.append(e)               # von mir nicht gelöscht: bleibt (nie still verwerfen)
        else:
            out.append(e)
    for e in mine or []:
        k = schluessel(e)
        if k not in gesehen:
            out.append(e)               # nur bei mir neu
    return out


def json_mischen(basis, theirs, mine):
    if not all(isinstance(x, dict) for x in (theirs, mine)):
        return mine
    basis = basis if isinstance(basis, dict) else {}
    out = dict(theirs)
    for k, v in mine.items():
        if k in basis and basis[k] == v:
            continue                    # nicht von mir geändert: Stand auf GitHub gilt
        t = theirs.get(k)
        if isinstance(v, list) and isinstance(t, list) and all(isinstance(e, dict) for e in v + t) and any(
                any(s in e for s in ("datei", "charge")) for e in v + t):
            out[k] = liste_mischen(basis.get(k), t, v)
        else:
            out[k] = v
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
            git("checkout", "--theirs", "--", p)
            print(f"Konflikt in {p}: eigener Stand übernommen (einziger Schreiber)")
        git("add", "--", p)
    return True


def main():
    git("config", "user.name", "pruefstand-bot")
    git("config", "user.email", "pruefstand-bot@users.noreply.github.com")
    git("add", "-A")
    if git("diff", "--cached", "--quiet", ok=True).returncode == 0:
        print("keine Änderung"); return 0
    git("commit", "-q", "-m", f"{PRAEFIX} {time.strftime('%Y-%m-%dT%H:%MZ', time.gmtime())} (GitHub Action)")
    for versuch in range(1, 6):
        try:
            if git("ls-remote", "--exit-code", "--heads", "origin", ZWEIG, ok=True).returncode == 0:
                git("fetch", "-q", "origin", f"+{ZWEIG}:{REF}")
                r = git("rebase", "-q", REF, ok=True)
                while r.returncode != 0:
                    if not konflikte_loesen():
                        git("rebase", "--abort", ok=True)
                        raise RuntimeError(f"Rebase gescheitert ohne lösbaren Konflikt: {r.stderr.strip()[-300:]}")
                    r = subprocess.run(["git", "-C", LERNEN, "-c", "core.editor=true", "rebase", "--continue"],
                                       capture_output=True, text=True)
            r = git("push", "-q", "origin", f"HEAD:{ZWEIG}", ok=True)
            if r.returncode == 0:
                print(f"eingecheckt auf {ZWEIG}: {git('rev-parse', '--short', 'HEAD').stdout.strip()} (Versuch {versuch})")
                return 0
            print(f"Versuch {versuch}: Push abgewiesen: {r.stderr.strip()[-300:]}")
        except RuntimeError as e:
            print(f"Versuch {versuch}: {e}")
        time.sleep(15 * versuch)
    print("Einchecken gescheitert"); return 1


if __name__ == "__main__":
    sys.exit(main())
