"""Lauscht auf dem ntfy-Kommando-Topic und laesst kommando.py antworten.

Bewusst ein eigener Prozess neben FastAPI: faellt der Listener aus, laeuft die
Belegverarbeitung unbeirrt weiter. Die Verbindung ist ein langlebiger Stream -
kein Polling, keine offene Portfreigabe.
"""
import os
import sys
import json
import time
import subprocess

import requests

import slog

BASIS = os.environ.get("NTFY_BASE", "http://ntfy:80").rstrip("/")
TOPIC = os.environ.get("NTFY_CMD_TOPIC", "finance-cmd")
USER = os.environ.get("NTFY_USER", "")
PASSWORT = os.environ.get("NTFY_PASSWORD", "")
WARTEN_NACH_FEHLER = 10


def verarbeite(nachricht):
    """kommando.py als eigenen Prozess starten - ein Absturz reisst den Listener
    dann nicht mit."""
    subprocess.run([sys.executable, "/app/kommando.py", nachricht], timeout=300, check=False)


def lausche():
    url = f"{BASIS}/{TOPIC}/json"
    auth = (USER, PASSWORT) if USER and PASSWORT else None
    with requests.get(url, auth=auth, stream=True, timeout=(10, None)) as r:
        r.raise_for_status()
        slog.log_event("listener_verbunden", topic=TOPIC)
        for zeile in r.iter_lines():
            if not zeile:
                continue
            try:
                daten = json.loads(zeile)
            except json.JSONDecodeError:
                continue
            if daten.get("event") != "message":
                continue          # keepalive und open ignorieren
            verarbeite(daten.get("message", ""))


def main():
    while True:
        try:
            lausche()
        except Exception as e:
            slog.log_event("listener_getrennt", error_type=type(e).__name__)
        time.sleep(WARTEN_NACH_FEHLER)


if __name__ == "__main__":
    main()
