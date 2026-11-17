"""Tests fuer ansible/roles/common/files/loki-umstellen.sh mit einem falschen docker."""
import os
import shutil
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "common" / "files" / "loki-umstellen.sh"
BASH = shutil.which("bash")

NEU = "http://homelab:geheim@192.0.2.60:3101/loki/api/v1/push"
ALT = "http://192.0.2.60:3100/loki/api/v1/push"

# Falsches docker: liest Container aus $FAKE_DIR/containers (id|treiber|url|compose-ordner|name)
# und protokolliert jedes "compose up" nach $FAKE_DIR/calls
FAKE_DOCKER = r'''#!/bin/bash
f="$FAKE_DIR/containers"
case "$1" in
  ps) cut -d'|' -f1 "$f" ;;
  inspect)
    fmt="$3"; id="$4"; line=$(grep "^$id|" "$f")
    IFS='|' read -r _ drv url dir name <<< "$line"
    case "$fmt" in
      *LogConfig.Type*) echo "$drv" ;;
      *loki-url*) echo "$url" ;;
      *working_dir*) echo "$dir" ;;
      *Name*) echo "/$name" ;;
    esac ;;
  compose) echo "$PWD $*" >> "$FAKE_DIR/calls" ;;
esac
'''


@pytest.fixture
def umgebung(tmp_path):
    if not BASH:
        pytest.skip("bash fehlt")
    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    docker = bin_dir / "docker"
    docker.write_text(FAKE_DOCKER, encoding="utf-8", newline="\n")
    docker.chmod(0o755)
    daemon = tmp_path / "daemon.json"
    daemon.write_text('{\n  "log-driver": "loki",\n  "log-opts": {\n    "loki-url": "%s",\n'
                      '    "loki-retries": "5"\n  }\n}\n' % NEU, encoding="utf-8", newline="\n")
    for d in ("app", "web"):
        (tmp_path / d).mkdir()

    def run(containers):
        (tmp_path / "containers").write_text(
            "".join("|".join(c) + "\n" for c in containers), encoding="utf-8", newline="\n")
        (tmp_path / "calls").write_text("", encoding="utf-8")
        env = dict(os.environ, PATH=str(bin_dir) + os.pathsep + os.environ["PATH"], FAKE_DIR=str(tmp_path),
                   DAEMON_JSON=str(daemon))
        r = subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True)
        calls = (tmp_path / "calls").read_text(encoding="utf-8").splitlines()
        return r, calls

    run.tmp = tmp_path
    return run


def p(tmp, d):
    return str(tmp / d).replace("\\", "/")


def test_nur_container_mit_altem_ziel_werden_neu_erstellt(umgebung):
    t = umgebung.tmp
    r, calls = umgebung([
        ("a1", "loki", ALT, p(t, "app"), "app-1"),
        ("a2", "loki", ALT, p(t, "app"), "app-2"),
        ("w1", "loki", NEU, p(t, "web"), "web-1"),
    ])
    assert r.returncode == 0, r.stderr
    assert len(calls) == 1 and "up -d --force-recreate --pull never" in calls[0]
    assert "neu erstellt: " + p(t, "app") in r.stdout


def test_alles_aktuell_nichts_zu_tun(umgebung):
    t = umgebung.tmp
    r, calls = umgebung([("w1", "loki", NEU, p(t, "web"), "web-1")])
    assert r.returncode == 0 and calls == [] and "neu erstellt" not in r.stdout


def test_andere_log_treiber_bleiben_unberuehrt(umgebung):
    t = umgebung.tmp
    r, calls = umgebung([("x1", "json-file", "", p(t, "app"), "x-1")])
    assert calls == [] and r.returncode == 0


def test_ohne_compose_nur_meldung(umgebung):
    r, calls = umgebung([("s1", "loki", ALT, "", "einzeln")])
    assert calls == [] and r.returncode == 0
    assert "einzeln" in r.stdout


def test_passwort_landet_nie_in_der_ausgabe(umgebung):
    t = umgebung.tmp
    r, _ = umgebung([("a1", "loki", ALT, p(t, "app"), "app-1"), ("s1", "loki", ALT, "", "einzeln")])
    assert "geheim" not in r.stdout + r.stderr
