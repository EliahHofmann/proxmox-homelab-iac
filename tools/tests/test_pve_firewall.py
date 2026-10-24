"""Tests fuer tools/firewall/pve_firewall.py (Firewall pro Gast als Code)."""
import copy
import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
spec = importlib.util.spec_from_file_location("pve_firewall", ROOT / "tools/firewall/pve_firewall.py")
fw = importlib.util.module_from_spec(spec)
spec.loader.exec_module(fw)

POLICY = fw.load_policy(ROOT / "firewall/policy.yml")


def policy(**mods):
    p = copy.deepcopy(POLICY)
    for name, mode in mods.items():
        p["guests"][name]["mode"] = mode
    return p


def rules(g, typ):
    return [r for r in g["rules"] if r["type"] == typ]


def allows(g, source, port, proto="tcp"):
    """Gibt es eine IN-ACCEPT-Regel ohne Log, die source auf port zulaesst?"""
    for r in rules(g, "in"):
        if r["action"] != "ACCEPT" or r.get("log", "nolog") != "nolog":
            continue
        if r.get("proto") != proto:
            continue
        if port is not None and str(port) not in r.get("dport", "").split(","):
            continue
        if source in r.get("source", "").split(","):
            return True
    return False


def test_owner_ipset_schliesst_infrastruktur_aus():
    g = fw.render_guest(POLICY, "qwen3")
    owner = g["ipsets"]["owner"]
    assert ("192.168.178.0/24", False) in owner
    excluded = {cidr for cidr, nomatch in owner if nomatch}
    for ip in ["192.168.178.1", "192.168.178.10", "192.168.178.11", "192.168.178.91",
               "192.168.178.178", "192.168.178.86", "192.168.178.61", "192.168.178.60"]:
        assert ip in excluded, ip
    # Der Tailscale-Router reicht Besitzer-Geraete durch und zaehlt deshalb als Besitzer
    assert "192.168.178.33" not in excluded


def test_gemeinsame_regeln():
    g = fw.render_guest(POLICY, "jellyfin")
    assert allows(g, "+owner", 22)
    assert allows(g, "192.168.178.61", 22)
    assert allows(g, "192.168.178.60", 9100)
    assert not allows(g, "192.168.178.86", 22)


def test_flusstabelle_beispiele():
    q = fw.render_guest(POLICY, "qwen3")
    assert allows(q, "192.168.178.86", 11434) and allows(q, "192.168.178.87", 11434)
    assert allows(q, "+owner", 11434)
    assert not allows(q, "192.168.178.31", 11434)
    p = fw.render_guest(POLICY, "paperless")
    assert allows(p, "192.168.178.10", 1025) and allows(p, "192.168.178.11", 1025)
    assert not allows(p, "192.168.178.85", 8010)
    a = fw.render_guest(POLICY, "adguard")
    assert allows(a, "192.168.178.0/24", 53, "udp") and allows(a, "192.168.178.0/24", 53, "tcp")
    m = fw.render_guest(POLICY, "monitoring")
    assert allows(m, "192.168.178.86", 3100) and allows(m, "192.168.178.33", 3100)


def test_beobachten_blockt_nie():
    g = fw.render_guest(policy(paperless="observe"), "paperless")
    assert g["options"]["policy_in"] == "ACCEPT"
    assert g["options"]["ipfilter"] == 0
    assert all(r["action"] == "ACCEPT" for r in g["rules"])
    last_in = rules(g, "in")[-1]
    assert last_in.get("log") == "info" and "source" not in last_in and "dport" not in last_in
    assert all(r.get("log") == "info" for r in rules(g, "out") if "dport" not in r)


def test_scharf_blockt_und_filtert_absender():
    g = fw.render_guest(policy(paperless="enforce"), "paperless")
    assert g["options"]["policy_in"] == "DROP"
    assert g["options"]["ipfilter"] == 1
    assert g["ipsets"]["ipfilter-net0"] == [("192.168.178.86", False)]
    assert all(r.get("log", "nolog") == "nolog" for r in rules(g, "in"))
    out = rules(g, "out")
    assert {"type": "out", "action": "DROP", "dest": "192.168.178.10,192.168.178.11"}.items() <= out[0].items()
    assert any(r["action"] == "DROP" and r.get("dest") == "+owner" for r in out)


def test_knotenzugang_nur_fuer_monitoring_und_runner():
    for name in ("monitoring", "runner"):
        out = rules(fw.render_guest(policy(**{name: "enforce"}), name), "out")
        assert out[0]["action"] == "ACCEPT" and out[0]["dport"] == "8006"
        assert out[1]["action"] == "DROP" and out[1]["dest"] == "192.168.178.10,192.168.178.11"
    out = rules(fw.render_guest(policy(qwen3="enforce"), "qwen3"), "out")
    assert not any(r["action"] == "ACCEPT" for r in out)


def test_tailscale_darf_zu_besitzer_geraeten():
    out = rules(fw.render_guest(policy(tailscale="enforce"), "tailscale"), "out")
    assert not any(r.get("dest") == "+owner" for r in out)


def test_unbekannter_absender_ist_fehler():
    p = policy()
    p["in"]["qwen3"].append({"port": 1, "from": ["gibtsnicht"]})
    with pytest.raises(ValueError):
        fw.render_guest(p, "qwen3")


def test_regeln_fuer_unbekannten_gast_sind_fehler():
    p = policy()
    p["in"]["gibtsnicht"] = [{"port": 1, "from": ["owner"]}]
    with pytest.raises(ValueError):
        fw.render_guest(p, "qwen3")


def test_quellen_passen_in_die_api_grenze():
    for name in POLICY["guests"]:
        for r in fw.render_guest(policy(**{name: "enforce"}), name)["rules"]:
            assert len(r.get("source", "")) <= 512 and len(r.get("dest", "")) <= 512
