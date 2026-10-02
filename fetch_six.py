#!/usr/bin/env python3
"""SIX-Archiv im öffentlichen Repo: STILLGELEGT (2.10.2026).

Das Archiv der SIX-Pflichtmeldungen läuft seit dem 2.10.2026 im privaten Repo «pruefstand-archiv»
(Entscheid Reto, 2.10.2026: Nutzungsbedingungen der SIX-Website nur für den persönlichen Gebrauch; Personendaten).
Dieses Skript holt nichts mehr. Es entfernt nur den Ordner data/six aus dem Arbeitsverzeichnis; der Datenspiegel
checkt die Löschung wie jede andere Änderung ein. Die Historie des Repos wird nicht angefasst.
"""
import os, shutil, sys

PFAD = os.path.join("data", "six")
if os.path.isdir(PFAD):
    shutil.rmtree(PFAD)
    print("SIX-Archiv stillgelegt: Ordner data/six entfernt (Archiv liegt im privaten Repo).", file=sys.stderr)
else:
    print("SIX-Archiv stillgelegt: nichts zu tun.", file=sys.stderr)
sys.exit(0)
