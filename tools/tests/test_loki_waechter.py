"""Prueft die Dateien, die die Monitoring-Rolle fuer den Loki-Waechter schreibt."""
from pathlib import Path

import yaml

TASKS = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "monitoring" / "tasks" / "main.yml"


def waechter_dateien():
    tasks = yaml.safe_load(TASKS.read_text(encoding="utf-8"))
    task = next(t for t in tasks if t.get("name") == "Loki-Waechter Konfiguration und Zugangsdaten")
    return {i["datei"]: i["inhalt"] for i in task["loop"]}


def test_htpasswd_endet_mit_zeilenumbruch_ohne_leerzeichen():
    # Ein angehaengtes Leerzeichen wird Teil des Hashes -> nginx meldet password mismatch
    inhalt = waechter_dateien()["htpasswd"]
    assert inhalt.endswith("\n")
    assert not inhalt.rstrip("\n").endswith(" ")
    assert inhalt.count("\n") == 1
