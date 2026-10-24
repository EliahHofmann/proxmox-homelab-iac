"""Tests fuer ansible/roles/tailscale/templates/docker-compose.yml.j2 (nur Beispielwerte)."""
from pathlib import Path

import jinja2
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "ansible/roles/tailscale/templates/docker-compose.yml.j2"


def dienst():
    ctx = {
        "tailscale_install_path": "/opt/tailscale",
        "tailscale_authkey": "tskey-example",
        "tailscale_routes": "192.0.2.0/24",
        "tailscale_tag": "tag:homelab",
    }
    text = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(TEMPLATE.read_text()).render(**ctx)
    return yaml.safe_load(text)["services"]["tailscale"]


def env():
    return dict(e.split("=", 1) for e in dienst()["environment"])


def test_userspace_und_host_netz():
    d = dienst()
    assert d["network_mode"] == "host"
    assert env().get("TS_USERSPACE", "true") == "true"
    assert "cap_add" not in d and "devices" not in d


def test_anmeldung_nur_einmal():
    assert env()["TS_AUTH_ONCE"] == "true"
    assert env()["TS_STATE_DIR"] == "/var/lib/tailscale"
    assert "/opt/tailscale/state:/var/lib/tailscale" in dienst()["volumes"]


def test_route_und_tag():
    e = env()
    assert e["TS_ROUTES"] == "192.0.2.0/24"
    assert "--advertise-tags=tag:homelab" in e["TS_EXTRA_ARGS"]
    assert "exit-node" not in e["TS_EXTRA_ARGS"]
    assert e["TS_HOSTNAME"] == "tailscale"
    assert e.get("TS_ACCEPT_DNS", "false") == "false"


def test_health_nur_lokal():
    e = env()
    assert e["TS_ENABLE_HEALTH_CHECK"] == "true"
    assert e["TS_LOCAL_ADDR_PORT"] == "127.0.0.1:9002"
    assert "http://127.0.0.1:9002/healthz" in " ".join(dienst()["healthcheck"]["test"])
