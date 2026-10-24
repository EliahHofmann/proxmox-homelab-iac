"""Gleicht die Proxmox-Firewall jedes Gastes mit firewall/policy.yml ab.

Ohne --apply wird nur angezeigt, was sich aendern wuerde (PR-Lauf). Verwaltet
werden pro Gast nur Optionen, Regeln und die IP-Sets "owner" und
"ipfilter-net0" - nichts auf Rechenzentrums-Ebene.

Zugang wie das Ansible-Inventory: PROXMOX_URL, PROXMOX_USER, PROXMOX_TOKEN_ID,
PROXMOX_TOKEN_SECRET; die Cluster-CA liegt in ansible/files/pve-root-ca.pem.
"""
import argparse
import json
import os
import ssl
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
MANAGED_IPSETS = ("owner", "ipfilter-net0")
RULE_KEYS = ("type", "action", "source", "dest", "proto", "dport", "log", "enable", "comment")


def load_policy(path):
    with open(path, encoding="utf-8") as f:
        return yaml.safe_load(f)


def _as_list(v):
    return v if isinstance(v, list) else [v]


def owner_ipset(policy):
    """Ganzes LAN, ohne Router, Knoten, reservierte Adressen und Gaeste.

    Gaeste mit owner_proxy (Tailscale) bleiben drin: sie reichen Verbindungen
    der Besitzer-Geraete durch.
    """
    entries = [(policy["lan"], False)]
    excluded = [policy["router"], *policy["nodes"], *policy.get("reserved", [])]
    excluded += [g["ip"] for g in policy["guests"].values() if not g.get("owner_proxy")]
    entries += [(ip, True) for ip in excluded]
    return entries


def _sources(policy, names):
    """Absender-Namen -> Liste von source-Werten (IP-Set-Verweis oder IP-Liste)."""
    ipset, ips = [], []
    for n in names:
        if n == "owner":
            ipset.append("+owner")
        elif n == "lan":
            ips.append(policy["lan"])
        elif n == "nodes":
            ips += policy["nodes"]
        elif n == "guests":
            ips += [g["ip"] for g in policy["guests"].values()]
        elif n in policy["guests"]:
            ips.append(policy["guests"][n]["ip"])
        else:
            raise ValueError(f"unbekannter Absender: {n}")
    return ipset + ([",".join(ips)] if ips else [])


def _in_rules(policy, entries):
    out = []
    for e in entries:
        protos = _as_list(e.get("proto", "tcp"))
        port = str(e["port"]) if "port" in e else None
        label = f"{port or '/'.join(protos)} von {', '.join(e['from'])}"
        for src in _sources(policy, e["from"]):
            for proto in protos:
                r = {"type": "in", "action": "ACCEPT", "source": src, "proto": proto}
                if port:
                    r["dport"] = port
                r["comment"] = label
                out.append(r)
    return out


def render_guest(policy, name):
    unknown = set(policy.get("in", {})) - set(policy["guests"])
    if unknown:
        raise ValueError(f"Regeln fuer unbekannte Gaeste: {sorted(unknown)}")
    g = policy["guests"][name]
    enforce = g["mode"] == "enforce"
    if g["mode"] not in ("observe", "enforce"):
        raise ValueError(f"{name}: mode muss observe oder enforce sein")
    nodes = ",".join(policy["nodes"])
    # Was im Beobachten-Modus geblockt wuerde, wird nur protokolliert
    block = {"action": "DROP"} if enforce else {"action": "ACCEPT", "log": "info"}

    rules = _in_rules(policy, policy["common_in"]) + _in_rules(policy, policy.get("in", {}).get(name, []))
    if not enforce:
        rules.append({"type": "in", "action": "ACCEPT", "log": "info", "comment": "beobachten: wuerde geblockt"})
    for a in policy.get("node_access", []):
        if a["guest"] == name:
            rules.append({"type": "out", "action": "ACCEPT", "dest": nodes, "proto": "tcp",
                          "dport": str(a["port"]), "comment": "Proxmox-API"})
    rules.append({"type": "out", **block, "dest": nodes, "comment": "keine Knoten"})
    if not g.get("owner_proxy"):
        rules.append({"type": "out", **block, "dest": "+owner", "comment": "keine Besitzer-Geraete"})
    for r in rules:
        r.setdefault("log", "nolog")
        r["enable"] = 1

    options = {
        "enable": 1,
        "policy_in": "DROP" if enforce else "ACCEPT",
        "policy_out": "ACCEPT",
        "ipfilter": 1 if enforce else 0,
        "macfilter": 1,
        "log_level_in": "info" if enforce else "nolog",
        "log_level_out": "nolog",
    }
    ipsets = {"owner": owner_ipset(policy), "ipfilter-net0": [(g["ip"], False)]}
    return {"options": options, "ipsets": ipsets, "rules": rules}
