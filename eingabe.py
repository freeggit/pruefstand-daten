#!/usr/bin/env python3
"""Prüfstand – Prüfsumme der massgeblichen Eingaben der Discovery (Verfassung V3.17, §4, E9 neu).

Die Suche läuft nach V3.17 nur, wenn sich eine massgebliche Eingabe geändert hat (oder am Montag als Kontrolllauf).
Massgeblich sind die Daten der Discovery bis 31.12.2020 (Familie S) bzw. 31.12.2000 (Familie L), so wie die
Suchmaschine sie nach Kürzung, Korrekturen und Verfügbarkeitsregeln tatsächlich verwendet, dazu Register,
Konfiguration, Code und Rechenumgebung. Neue Kurse ab 1.1.2021 ändern diese Prüfsumme nicht.

Gleitkommazahlen werden vor dem Hashen auf 12 signifikante Stellen gerundet (Exponent und ganzzahlige Mantisse).
Grund: Dieselbe Zahl kann nach dem Lesen und Schreiben einer Datei in der letzten Binärstelle abweichen. Eine echte Revision
kleiner als rund 1e-12 relativ löst darum keinen Lauf aus (offengelegt, V3.17 §4). Angepasste Kurse gehen nur als
Rohkurse und Faktorsprünge ein (siehe suchmaschine.py, eingaben_schreiben).
"""
import hashlib
import numpy as np
import pandas as pd

STELLEN = 12   # signifikante Stellen


def _zahlen(a):
    a = np.asarray(a)
    if a.dtype.kind in "iub":   # ganze Zahlen wie Gleitkommazahlen: gleicher Wert, gleiche Prüfsumme, unabhängig vom Datentyp
        a = a.astype(float)
    if a.dtype.kind == "f":
        a = a.astype(float).ravel()
        fin = np.isfinite(a)
        code = np.where(np.isnan(a), 1, np.where(a == np.inf, 2, np.where(a == -np.inf, 3, 0))).astype(np.int8)
        e = np.zeros(a.shape, dtype=np.int64); m = np.zeros(a.shape, dtype=np.int64)
        nz = fin & (a != 0)
        if nz.any():
            ee = np.floor(np.log10(np.abs(a[nz]))).astype(np.int64)
            mm = np.round(a[nz] * 10.0 ** (STELLEN - 1 - ee)).astype(np.int64)
            ueber = np.abs(mm) >= 10 ** STELLEN            # Rundung auf die nächste Zehnerpotenz
            mm[ueber] //= 10; ee[ueber] += 1
            e[nz], m[nz] = ee, mm
        return code.tobytes() + e.tobytes() + m.tobytes()
    return "\x1f".join(map(str, a.tolist())).encode("utf-8")


def _fuettern(m, obj, tiefe=0):
    """Schreibt obj deterministisch in den Hash m. Unterstützt Series, DataFrame, Index, ndarray, dict, list, tuple, Skalare."""
    if tiefe > 20:
        raise ValueError("zu tief verschachtelt")
    if isinstance(obj, pd.Series):
        m.update(b"S"); _fuettern(m, obj.index, tiefe + 1); m.update(_zahlen(obj.values)); return
    if isinstance(obj, pd.DataFrame):
        m.update(b"D"); _fuettern(m, obj.index, tiefe + 1); m.update("\x1f".join(map(str, obj.columns)).encode("utf-8"))
        for c in obj.columns:
            m.update(_zahlen(obj[c].values))
        return
    if isinstance(obj, pd.DatetimeIndex):
        m.update(b"T"); m.update(obj.asi8.tobytes()); return
    if isinstance(obj, pd.Index):
        m.update(b"I"); m.update(_zahlen(obj.values)); return
    if isinstance(obj, np.ndarray):
        m.update(b"A"); m.update(str(obj.shape).encode()); m.update(_zahlen(obj)); return
    if isinstance(obj, dict):
        m.update(b"{")
        for k in sorted(obj, key=repr):
            m.update(repr(k).encode("utf-8")); _fuettern(m, obj[k], tiefe + 1)
        m.update(b"}"); return
    if isinstance(obj, (list, tuple)):
        m.update(b"[")
        for x in obj:
            _fuettern(m, x, tiefe + 1)
        m.update(b"]"); return
    if isinstance(obj, (set, frozenset)):
        _fuettern(m, sorted(obj, key=repr), tiefe + 1); return
    if isinstance(obj, float):
        m.update(_zahlen(np.array([obj]))); return
    if callable(obj):
        return   # Funktionen (z. B. FAM["S"]["rand"]) sind Code und stehen im Code-Hash
    m.update(repr(obj).encode("utf-8"))


def pruefsumme(obj):
    m = hashlib.sha256()
    _fuettern(m, obj)
    return m.hexdigest()[:16]
