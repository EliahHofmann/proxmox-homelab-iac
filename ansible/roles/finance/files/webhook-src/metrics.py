"""Prometheus-Metriken fuer die Finance-Automation ("Finance Automation Health").

Datenschutz-Regel (bewusst): Es werden AUSSCHLIESSLICH Betriebs- und
Datenqualitaets-Metriken exportiert. NIEMALS Betraege, Haendler, IBANs,
Kontonummern, Rechnungsnummern, Dokumenttitel oder OCR-Text - weder als
Metrik-Wert noch als Label. Labels sind statisch oder es gibt keine.

Architektur: Nur der finance-webhook ist ein Langlaeufer (PID 1), dort leben die
In-Process-Counter/Histogramme der Beleg-Pipeline. Die Cron-Jobs (bank-import,
dedupe, advisor, categorize) laufen als SEPARATE Prozesse und koennen nicht in
denselben RAM-Registry schreiben. Sie legen ihren Zustand daher als kleine
JSON-Dateien unter METRICS_STATE_DIR ab; der StateFileCollector liest sie beim
Scrape und rendert sie als Prometheus-Metriken.
"""
import os
import json
import time
import glob
import tempfile

from prometheus_client import (
    Counter, Gauge, Histogram, CollectorRegistry, generate_latest, CONTENT_TYPE_LATEST,
)
from prometheus_client.core import CounterMetricFamily, GaugeMetricFamily

REGISTRY = CollectorRegistry()
STATE_DIR = os.environ.get("METRICS_STATE_DIR", "/app/state")

# ---------------------------------------------------------------------------
# In-Process-Metriken (Beleg-Pipeline im Webhook, PID 1)
# ---------------------------------------------------------------------------
webhook_received = Counter(
    "finance_paperless_webhook_received_total",
    "Von Paperless empfangene Webhook-Events (document_consumed).", registry=REGISTRY)
webhook_invalid = Counter(
    "finance_paperless_webhook_invalid_total",
    "Verworfene/ungueltige Webhook-Requests.", registry=REGISTRY)
extraction_success = Counter(
    "finance_invoice_extraction_success_total",
    "Erfolgreiche KI-Extraktionen mit brauchbarem Betrag.", registry=REGISTRY)
extraction_failed = Counter(
    "finance_invoice_extraction_failed_total",
    "Fehlgeschlagene KI-Extraktionen (Fehlerklasse steht im Log, nicht als Label).",
    registry=REGISTRY)
firefly_create_success = Counter(
    "finance_firefly_transaction_create_success_total",
    "Erfolgreich in Firefly angelegte Transaktionen.", registry=REGISTRY)
firefly_create_failed = Counter(
    "finance_firefly_transaction_create_failed_total",
    "Fehlgeschlagene Firefly-Transaktions-Erstellungen.", registry=REGISTRY)
last_webhook_ts = Gauge(
    "finance_last_paperless_webhook_timestamp",
    "Unix-Zeit des zuletzt empfangenen Paperless-Webhooks.", registry=REGISTRY)

ollama_duration = Histogram(
    "finance_ollama_request_duration_seconds",
    "Dauer eines Ollama-Extraktions-Requests in Sekunden.",
    buckets=(1, 5, 10, 20, 30, 60, 90, 120, 180), registry=REGISTRY)
paperless_duration = Histogram(
    "finance_paperless_api_request_duration_seconds",
    "Dauer eines Paperless-API-Requests in Sekunden.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30), registry=REGISTRY)
firefly_duration = Histogram(
    "finance_firefly_api_request_duration_seconds",
    "Dauer eines Firefly-API-Requests in Sekunden.",
    buckets=(0.1, 0.25, 0.5, 1, 2, 5, 10, 30), registry=REGISTRY)


class timer:
    """Kontext-Manager: misst die Dauer und legt sie in einem Histogram ab.

    with timer(ollama_duration):
        ...
    """

    def __init__(self, histogram):
        self._h = histogram

    def __enter__(self):
        self._t0 = time.perf_counter()
        return self

    def __exit__(self, *exc):
        self._h.observe(time.perf_counter() - self._t0)
        return False


# ---------------------------------------------------------------------------
# Cross-Prozess-Metriken (Cron-Jobs -> JSON-State-Dateien)
# ---------------------------------------------------------------------------
# Metrik-Namen je Job zentral, damit Schreiber (Jobs) und Leser (Collector)
# garantiert dieselben Namen verwenden. dedupe zaehlt Matches statt "runs".
JOB_SPECS = {
    "bank_import": {
        "success": "finance_bank_import_success_total",
        "failed": "finance_bank_import_failed_total",
        "duration": "finance_bank_import_duration_seconds",
        "last_success": "finance_last_successful_bank_import_timestamp",
    },
    "dedupe": {
        "success": "finance_dedupe_matches_total",
        "failed": "finance_dedupe_failed_total",
        "duration": "finance_dedupe_duration_seconds",
        "last_success": "finance_last_successful_dedupe_timestamp",
    },
    "advisor": {
        "success": "finance_advisor_run_success_total",
        "failed": "finance_advisor_run_failed_total",
        "duration": "finance_advisor_duration_seconds",
        "last_success": "finance_last_successful_advisor_run_timestamp",
    },
    "categorize": {
        "success": "finance_categorize_run_success_total",
        "failed": "finance_categorize_run_failed_total",
        "duration": "finance_categorize_duration_seconds",
        "last_success": "finance_last_successful_categorize_timestamp",
    },
}

# Hilfetexte fuer die vom Collector erzeugten Familien (best effort).
_METRIC_HELP = {
    "finance_bank_import_success_total": "Erfolgreiche Bank-Import-Laeufe.",
    "finance_bank_import_failed_total": "Fehlgeschlagene Bank-Import-Laeufe.",
    "finance_bank_import_duration_seconds": "Dauer des letzten Bank-Imports in Sekunden.",
    "finance_last_successful_bank_import_timestamp": "Unix-Zeit des letzten erfolgreichen Bank-Imports.",
    "finance_dedupe_matches_total": "Anzahl Bank<->Beleg-Matches insgesamt.",
    "finance_dedupe_failed_total": "Fehlgeschlagene Dedupe-Laeufe.",
    "finance_dedupe_duration_seconds": "Dauer des letzten Dedupe-Laufs in Sekunden.",
    "finance_last_successful_dedupe_timestamp": "Unix-Zeit des letzten erfolgreichen Dedupe-Laufs.",
    "finance_dedupe_unmatched_receipts": "Unverifizierte Belege ohne Match nach dem Lauf.",
    "finance_receipts_needing_review": "Junge, unverifizierte Belege ohne Match (Handlungsbedarf).",
    "finance_advisor_run_success_total": "Erfolgreiche Advisor-Laeufe.",
    "finance_advisor_run_failed_total": "Fehlgeschlagene Advisor-Laeufe.",
    "finance_advisor_duration_seconds": "Dauer des letzten Advisor-Laufs in Sekunden.",
    "finance_last_successful_advisor_run_timestamp": "Unix-Zeit des letzten erfolgreichen Advisor-Laufs.",
    "finance_ntfy_push_success_total": "Erfolgreiche ntfy-Pushes.",
    "finance_ntfy_push_failed_total": "Fehlgeschlagene ntfy-Pushes.",
    "finance_categorize_run_success_total": "Erfolgreiche Kategorisierungs-Laeufe.",
    "finance_categorize_run_failed_total": "Fehlgeschlagene Kategorisierungs-Laeufe.",
    "finance_categorize_duration_seconds": "Dauer des letzten Kategorisierungs-Laufs in Sekunden.",
    "finance_last_successful_categorize_timestamp": "Unix-Zeit des letzten erfolgreichen Kategorisierungs-Laufs.",
    "finance_uncategorized_transactions_count": "Bank-Buchungen ohne Kategorie nach dem Lauf.",
}


def _empty_state():
    return {"counters": {}, "gauges": {}}


def _load_state(path):
    try:
        with open(path, "r", encoding="utf-8") as fh:
            data = json.load(fh)
        if not isinstance(data, dict):
            return _empty_state()
        data.setdefault("counters", {})
        data.setdefault("gauges", {})
        return data
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return _empty_state()


def _atomic_write(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, ensure_ascii=False)
        os.replace(tmp, path)
    finally:
        if os.path.exists(tmp):
            os.remove(tmp)


class JobMetrics:
    """Zustand eines Cron-Jobs als JSON-State-Datei (read-modify-write).

    Counter sind kumulativ (nur wachsend, solange die Datei existiert), Gauges
    werden ueberschrieben. Am Ende save() aufrufen.
    """

    def __init__(self, job, state_dir=None):
        self.job = job
        self.dir = state_dir or STATE_DIR
        self.path = os.path.join(self.dir, "%s.json" % job)
        self.data = _load_state(self.path)

    def inc(self, name, by=1):
        self.data["counters"][name] = self.data["counters"].get(name, 0) + by
        return self

    def set_gauge(self, name, value):
        self.data["gauges"][name] = value
        return self

    def record_success(self, duration_seconds):
        """Standard-Lauf: success-Counter +1, Dauer + Zeitstempel setzen."""
        spec = JOB_SPECS[self.job]
        self.inc(spec["success"])
        self.set_gauge(spec["duration"], round(duration_seconds, 3))
        self.set_gauge(spec["last_success"], time.time())
        return self

    def mark_success_meta(self, duration_seconds):
        """Nur Dauer + Erfolgs-Zeitstempel setzen (ohne success-Counter).

        Fuer dedupe, wo der 'Erfolg' die Zahl der Matches ist, nicht ein Run.
        """
        spec = JOB_SPECS[self.job]
        self.set_gauge(spec["duration"], round(duration_seconds, 3))
        self.set_gauge(spec["last_success"], time.time())
        return self

    def record_failure(self, duration_seconds=None):
        spec = JOB_SPECS[self.job]
        self.inc(spec["failed"])
        if duration_seconds is not None:
            self.set_gauge(spec["duration"], round(duration_seconds, 3))
        return self

    def save(self):
        _atomic_write(self.path, self.data)


class StateFileCollector:
    """Liest beim Scrape alle Job-State-Dateien und rendert sie als Metriken."""

    def __init__(self, state_dir=None):
        self.dir = state_dir or STATE_DIR

    def collect(self):
        counters = {}
        gauges = {}
        for path in sorted(glob.glob(os.path.join(self.dir, "*.json"))):
            state = _load_state(path)
            for name, val in state.get("counters", {}).items():
                counters[name] = counters.get(name, 0) + val
            for name, val in state.get("gauges", {}).items():
                gauges[name] = val  # letzter Wert gewinnt (Namen sind job-eindeutig)
        for name, val in sorted(counters.items()):
            # CounterMetricFamily haengt selbst "_total" an -> Basisname uebergeben.
            base = name[:-6] if name.endswith("_total") else name
            fam = CounterMetricFamily(base, _METRIC_HELP.get(name, name))
            fam.add_metric([], val)
            yield fam
        for name, val in sorted(gauges.items()):
            fam = GaugeMetricFamily(name, _METRIC_HELP.get(name, name))
            fam.add_metric([], val)
            yield fam


REGISTRY.register(StateFileCollector())


def render():
    """(bytes, content_type) fuer den /metrics-Endpoint."""
    return generate_latest(REGISTRY), CONTENT_TYPE_LATEST
