#!/usr/bin/env python3
"""Vorfassungspruefung fuer Scout-Reihen (7.11.2026, Vorschlaege 17 und 20; Reto: "freigeben").

Anlass: Gegenpruefungen vom 3.11. und 6.11.2026 (gp_2026-11-03_1 FDA, gp_2026-11-06_1 WASDE). Scouts mit
Seitendurchlauf verloren still Termine, weil eine leere Seite als Ende der Liste oder als Luecke galt.
Grundsatz: Ein Abruffehler darf nie als Daten erscheinen, unabhaengig davon, was die Daten zeigen.

Regel A (in den Skripten selbst): Eine leere Seite vor der letzten ist ein Abruffehler. Meldet die Quelle eine
Gesamtzahl, sind weniger geholte Seiten oder Datensaetze ebenfalls ein Abruffehler.

Regel B (dieses Modul): Vor dem Schreiben vergleicht ein Skript jede Reihe mit der bisherigen Datei. Bis zum
Stichtag 31.12.2020 darf kein Ereignis wegfallen. Sonst bricht das Skript ab, bevor es eine Datei schreibt;
run_all.py laesst dann die bisherigen Dateien stehen und traegt den Fehler ins Manifest ein.
- art "ereignis": Ein Tag mit Wert ungleich 0 darf keinen kleineren Wert erhalten und nicht fehlen
  (0/1-Termine, Zaehlungen).
- art "vorhanden": Ein Tag mit Wert darf nicht fehlen (Mittelwerte, Quoten).
- art "summe": Die Summe bis zum Stichtag darf hoechstens um 1% sinken (Reihen, deren Ereignisse zwischen
  Laeufen um einen Tag wandern, z.B. NTSB).
Fehlt die bisherige Datei oder ist sie unlesbar, entfaellt der Vergleich (erste Fassung).

Gewollte Korrekturen (z.B. ein Termin, der nachweislich keiner ist): Eintrag in quellen/vorfassung_ausnahmen.json
im Format {"<id>:<reihe>": {"<JJJJ-MM-TT>": "<Grund und Freigabe>"}}, nur mit Freigabe von Reto.
"""
import gzip
import json
import os

STICHTAG = "2020-12-31"
GRENZE_SUMME = 0.01
AUSNAHMEN = os.path.join(os.path.dirname(os.path.abspath(__file__)), "vorfassung_ausnahmen.json")


def _iso(d):
    return d.isoformat() if hasattr(d, "isoformat") else str(d)[:10]


def bisherige(pfad):
    """Werte bis zum Stichtag aus der bisherigen Datei als {JJJJ-MM-TT: Zahl}; None, wenn sie fehlt oder
    unlesbar ist."""
    if not os.path.isfile(pfad):
        return None
    werte = {}
    try:
        with gzip.open(pfad, "rt", encoding="utf-8") as f:
            next(f, None)
            for zeile in f:
                d, _, v = zeile.strip().partition(",")
                if not d or d[:10] > STICHTAG:
                    continue
                try:
                    werte[d[:10]] = float(v)
                except ValueError:
                    continue
    except (OSError, EOFError, UnicodeDecodeError):
        return None
    return werte


def _ausnahmen(schluessel):
    try:
        with open(AUSNAHMEN, encoding="utf-8") as f:
            return set(json.load(f).get(schluessel) or {})
    except (OSError, ValueError, AttributeError, TypeError):
        return set()


def pruefe(pfad, zeilen, schluessel, art="ereignis"):
    """Bricht mit SystemExit ab, wenn gegenueber der bisherigen Datei ein Ereignis bis zum Stichtag wegfaellt.
    zeilen: Paare (datum, wert), datum als date oder ISO-Text; fehlende Tage zaehlen als 0."""
    alt = bisherige(pfad)
    if not alt:
        return
    neu = {}
    for d, v in zeilen:
        iso = _iso(d)
        if iso <= STICHTAG:
            try:
                neu[iso] = float(v)
            except (TypeError, ValueError):
                continue
    if art == "summe":
        sa, sn = sum(alt.values()), sum(neu.values())
        if sa > 0 and sn < (1 - GRENZE_SUMME) * sa:
            raise SystemExit("Abruffehler %s: Summe bis 2020 %g statt %g in der Vorfassung; bisherige Datei bleibt"
                             % (schluessel, sn, sa))
        return
    erlaubt = _ausnahmen(schluessel)
    if art == "vorhanden":
        weg = sorted(d for d in alt if d not in neu and d not in erlaubt)
        was = "fehlen gegenueber der Vorfassung"
    else:
        weg = sorted(d for d, v in alt.items() if v and neu.get(d, 0.0) < v and d not in erlaubt)
        was = "mit weniger Ereignissen als in der Vorfassung"
    if weg:
        raise SystemExit("Abruffehler %s: %d Tage bis 2020 %s (%s%s); bisherige Datei bleibt"
                         % (schluessel, len(weg), was, ", ".join(weg[:5]), " ..." if len(weg) > 5 else ""))
