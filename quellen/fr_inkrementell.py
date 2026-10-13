#!/usr/bin/env python3
"""Federal Register: inkrementelle Auffrischung (13.10.2026).

Anlass: Seit dem 12.10.2026 antwortet die Federal-Register-API auf die Abrufe des Quellenscouts mit HTTP 403.
Jedes Skript holte bei jeder Auffrischung (alle 4 Stunden) die ganze Historie ab 1994 neu, Jahr fuer Jahr und
Dokumenttyp fuer Dokumenttyp: rund 2'000 Anfragen je Lauf, rund 12'000 pro Tag. Das ist die wahrscheinliche
Ursache der Sperre (Missbrauchsschutz), belegt ist sie nicht.

Neu: Abgeschlossene Jahre werden aus der bestehenden Datei uebernommen. Abgefragt werden nur das Vorjahr und das
laufende Jahr (spaete Nachtraege im Vorjahr bleiben erfasst). Fehlt die Datei oder beginnt sie nicht am
1. Januar des Startjahres, wird wie bisher die ganze Historie geholt. Zwischen zwei Anfragen liegt eine Pause.
"""
import datetime
import gzip
import io
import os
import time

PAUSE_S = 0.5   # Pause zwischen zwei Anfragen an die API


def plan(pfad, start_year, current_year):
    """Gibt (alte_zaehlungen, jahre) zurueck. alte_zaehlungen: {iso-datum: anzahl} fuer Tage vor dem 1.1. des
    Vorjahres aus der bestehenden Datei; jahre: die abzufragenden Jahre."""
    erstes_neu = current_year - 1
    alle = list(range(start_year, current_year + 1))
    if not os.path.isfile(pfad):
        return {}, alle
    try:
        with gzip.open(pfad, "rt", encoding="utf-8") as f:
            zeilen = f.read().splitlines()
    except (OSError, EOFError, UnicodeDecodeError):
        return {}, alle
    if len(zeilen) < 2 or zeilen[0].strip() != "datum,wert":
        return {}, alle
    alt = {}
    for z in zeilen[1:]:
        try:
            d, v = z.split(",", 1)
            datetime.date.fromisoformat(d)
            alt[d] = int(float(v))
        except ValueError:
            return {}, alle
    if not alt or min(alt) != "%04d-01-01" % start_year:
        return {}, alle
    grenze = "%04d-01-01" % erstes_neu
    if max(alt) < grenze:          # Datei endet vor dem Vorjahr: Luecke, darum ganze Historie
        return {}, alle
    alt = {d: v for d, v in alt.items() if d < grenze}
    return alt, [y for y in alle if y >= erstes_neu]


def pause():
    time.sleep(PAUSE_S)
