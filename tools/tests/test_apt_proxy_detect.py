"""Tests fuer ansible/roles/common/files/apt-proxy-detect (Rueckfall auf DIRECT)."""
import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest

SCRIPT = Path(__file__).resolve().parents[2] / "ansible" / "roles" / "common" / "files" / "apt-proxy-detect"
BASH = shutil.which("bash")


def run(host, port):
    if not BASH:
        pytest.skip("bash fehlt")
    env = dict(os.environ, APT_PROXY_HOST=host, APT_PROXY_PORT=str(port))
    return subprocess.run([BASH, str(SCRIPT)], env=env, capture_output=True, text=True, timeout=10)


def test_erreichbarer_zwischenspeicher_wird_benutzt():
    srv = socket.socket()
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        r = run("127.0.0.1", port)
    finally:
        srv.close()
    assert r.stdout.strip() == "http://127.0.0.1:%d" % port


def test_nicht_erreichbar_heisst_direkt():
    # 192.0.2.0/24 ist ein Dokumentationsnetz, dort antwortet niemand
    r = run("192.0.2.1", 3142)
    assert r.returncode == 0
    assert r.stdout.strip() == "DIRECT"
