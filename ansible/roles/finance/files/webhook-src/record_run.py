"""CLI, um den Ausgang eines externen Job-Laufs als Metrik festzuhalten.

Wird vom Host-Cron (bank-import.sh) via `docker exec finance-webhook` aufgerufen,
weil das Shell-Skript selbst keine Prometheus-Metriken exportieren kann. Schreibt
in die gemeinsame State-Datei, die der /metrics-Endpoint des Webhooks liest.

Beispiel:
  python record_run.py --job bank_import --status success --duration 12.3
  python record_run.py --job bank_import --status failed
"""
import sys
import argparse

from metrics import JobMetrics, JOB_SPECS


def main(argv=None):
    p = argparse.ArgumentParser()
    p.add_argument("--job", required=True, choices=sorted(JOB_SPECS.keys()))
    p.add_argument("--status", required=True, choices=["success", "failed"])
    p.add_argument("--duration", type=float, default=None,
                   help="Laufzeit in Sekunden (optional).")
    args = p.parse_args(argv)

    m = JobMetrics(args.job)
    if args.status == "success":
        m.record_success(args.duration if args.duration is not None else 0.0)
    else:
        m.record_failure(args.duration)
    m.save()
    return 0


if __name__ == "__main__":
    sys.exit(main())
