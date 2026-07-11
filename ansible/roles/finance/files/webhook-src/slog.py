"""Strukturierte JSON-Logs auf stdout.

Der finance-webhook laeuft unter dem globalen Loki-Docker-Logging-Driver
(siehe common-Rolle, daemon.json) -> stdout wird automatisch nach Loki geshippt.
Cron-Job-Ausgaben (docker exec) landen im Cron-Log; ihre Kennzahlen kommen ueber
Prometheus (metrics.py), nicht ueber Loki.

Datenschutz: In Logs gehoeren KEINE Betraege, OCR-Texte, Rechnungstitel,
Haendlernamen, IBANs, Verwendungszwecke, Tokens oder Keys. Als Sicherheitsnetz
verwirft log_event() Felder mit sensiblen Schluesselnamen. Wird ein Haendlerbezug
zum Debuggen gebraucht, nur den gesalzenen Hash (merchant_hash) loggen.
"""
import os
import sys
import json
import time
import hashlib

LOG_SALT = os.environ.get("LOG_SALT", "")

# Feldnamen, die niemals im Klartext geloggt werden duerfen (Sicherheitsnetz).
_SENSITIVE = {
    "amount", "betrag", "betrag_euro", "gesamtbetrag", "sum", "summe",
    "ocr", "ocr_text", "text", "content",
    "iban", "kontonummer", "account_number", "verwendungszweck", "reference",
    "merchant", "haendler", "händler", "destination_name", "source_name",
    "title", "titel", "description", "beschreibung", "notes", "notiz",
    "token", "secret", "key", "private_key", "password", "passwort",
    "rechnungsnummer", "invoice_number",
}


def merchant_hash(name):
    """Gesalzener, gekuerzter Hash eines Haendlernamens fuer Debugging-Bezug."""
    norm = (name or "").strip().lower()
    return hashlib.sha256((LOG_SALT + norm).encode("utf-8")).hexdigest()[:12]


def sanitize(fields):
    """Entfernt Felder mit sensiblem Schluesselnamen (case-insensitive)."""
    return {k: v for k, v in fields.items() if k.strip().lower() not in _SENSITIVE}


def log_event(event, _stream=None, **fields):
    """Schreibt eine JSON-Logzeile: {"ts":..., "event":..., <safe fields>}."""
    record = {"ts": round(time.time(), 3), "event": event}
    record.update(sanitize(fields))
    line = json.dumps(record, ensure_ascii=False)
    stream = _stream or sys.stdout
    stream.write(line + "\n")
    stream.flush()
    return record
