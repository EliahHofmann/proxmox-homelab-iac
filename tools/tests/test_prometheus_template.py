"""Tests fuer ansible/roles/monitoring/templates/prometheus.yml.j2 (nur Beispielwerte)."""
from pathlib import Path

import jinja2
import yaml

TEMPLATE = Path(__file__).resolve().parents[2] / "ansible/roles/monitoring/templates/prometheus.yml.j2"


def render(**extra):
    hostvars = {"web": {"ansible_host": "192.0.2.10"},
                "Minecraft": {"ansible_host": "192.0.2.91"},
                "fin": {"ansible_host": "192.0.2.87"}}
    ctx = {
        "groups": {"proxmox_all_lxc": ["web", "Minecraft"], "proxmox_all_qemu": [],
                   "tag_actualbudget": ["fin"]},
        "hostvars": hostvars,
        "monitoring_excluded_hosts": ["Kali-Linux-Prax", "Sandbox", "Minecraft"],
        "proxmox_node_ips": ["192.0.2.1", "192.0.2.2"],
    }
    ctx.update(extra)
    text = jinja2.Environment(undefined=jinja2.StrictUndefined).from_string(TEMPLATE.read_text()).render(**ctx)
    return yaml.safe_load(text)


def job(cfg, name):
    return next(j for j in cfg["scrape_configs"] if j["job_name"] == name)


def test_ausgeschlossene_hosts_werden_nicht_gescrapt():
    ziele = job(render(), "homelab-nodes")["static_configs"][0]["targets"]
    assert "192.0.2.91:9100" not in ziele
    assert "192.0.2.10:9100" in ziele


def test_beide_proxmox_knoten_sind_ziele():
    ziele = job(render(), "proxmox")["static_configs"][0]["targets"]
    assert ziele == ["192.0.2.1", "192.0.2.2"]


def test_alertmanager_und_regeln_sind_verdrahtet():
    cfg = render()
    assert cfg["rule_files"] == ["/etc/prometheus/rules/*.yml"]
    assert cfg["alerting"]["alertmanagers"][0]["static_configs"][0]["targets"] == ["alertmanager:9093"]
