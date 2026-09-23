#!/usr/bin/env bash
# Prüfstand: Strom-Reihen (energy-charts) aus einer Claude-Code-Routine holen.
# Ablage auf dem eigenen Zweig claude/daten-energie (nur data/hr/energie + manifest_energie.json).
# Grund: energy-charts sperrt die GitHub-Actions-IPs (429); Routinen dürfen nur auf claude/-Zweige schreiben.
set -euo pipefail
ZWEIG=claude/daten-energie
REPO=$(git rev-parse --show-toplevel)
SKRIPT="$REPO/fetch_hr.py"
W=$(mktemp -d)/energie
git -C "$REPO" worktree prune
git -C "$REPO" config user.name  >/dev/null || git -C "$REPO" config user.name  "pruefstand-routine"
git -C "$REPO" config user.email >/dev/null || git -C "$REPO" config user.email "pruefstand-routine@users.noreply.github.com"

if git -C "$REPO" ls-remote --exit-code --heads origin "$ZWEIG" >/dev/null 2>&1; then
  git -C "$REPO" fetch -q origin "$ZWEIG"
  git -C "$REPO" worktree add -q --detach "$W" "origin/$ZWEIG"
else
  git -C "$REPO" worktree add -q --detach "$W"
  git -C "$W" checkout -q --orphan "energie-neu-$$"
  git -C "$W" rm -rq --cached . && find "$W" -mindepth 1 -maxdepth 1 ! -name .git -exec rm -rf {} +
fi

cd "$W"
HR_TEILE=energie HR_MANIFEST=manifest_energie.json HR_BUDGET_MIN="${HR_BUDGET_MIN:-8}" python3 "$SKRIPT"

git add -A data
if git diff --cached --quiet; then echo "ERGEBNIS: keine Änderung"; exit 0; fi
git commit -qm "Strom-Reihen $(date -u +%Y-%m-%dT%H:%MZ)"
git push -q origin "HEAD:$ZWEIG"
echo "ERGEBNIS: gepusht $(git rev-parse --short HEAD) auf $ZWEIG"
python3 - <<'PY'
import json
m = json.load(open("data/hr/manifest_energie.json"))
for k, v in m["reihen"].items():
    print(f"{k}: {len(v.get('dateien', []))} Jahresdateien, {v.get('erste')} bis {v.get('letzte')}", ("| Fehler: " + v["fehler"][:80]) if v.get("fehler") else "")
print("Zeitbudget erschöpft, Rest folgt im nächsten Lauf" if m.get("zeitbudget_erschoepft") else "vollständig")
PY
