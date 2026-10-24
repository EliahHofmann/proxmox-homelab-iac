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


# --- Abgleich mit der API ---------------------------------------------------

OPTION_DEFAULTS = {"enable": 0, "policy_in": "DROP", "policy_out": "ACCEPT", "ipfilter": 0,
                   "macfilter": 1, "log_level_in": "nolog", "log_level_out": "nolog"}
INT_OPTIONS = ("enable", "ipfilter", "macfilter")


def unquote(s):
    return urllib.parse.unquote(s)


def normalize_rule(r):
    """API-Regel -> Vergleichsform (ohne pos, digest, ipversion)."""
    n = {k: r[k] for k in RULE_KEYS if r.get(k) not in (None, "")}
    n.setdefault("log", "nolog")
    n["enable"] = int(n.get("enable", 0))
    if "dport" in n:
        n["dport"] = str(n["dport"])
    return n


def normalize_options(o):
    n = {k: o.get(k, d) for k, d in OPTION_DEFAULTS.items()}
    for k in INT_OPTIONS:
        n[k] = int(n[k])
    return n


def _sync_ipsets(api, base, desired, apply):
    changes = []
    existing = {s["name"] for s in api.get(f"{base}/ipset")}
    for name, entries in desired.items():
        want = set(entries)
        have = set()
        if name in existing:
            have = {(e["cidr"], bool(int(e.get("nomatch", 0)))) for e in api.get(f"{base}/ipset/{name}")}
        else:
            changes.append(f"IP-Set {name} anlegen")
            if apply:
                api.post(f"{base}/ipset", {"name": name})
        for cidr, nomatch in sorted(have - want):
            changes.append(f"IP-Set {name}: {'!' if nomatch else ''}{cidr} entfernen")
            if apply:
                api.delete(f"{base}/ipset/{name}/{urllib.parse.quote(cidr, safe='')}")
        for cidr, nomatch in sorted(want - have):
            changes.append(f"IP-Set {name}: {'!' if nomatch else ''}{cidr} dazu")
            if apply:
                api.post(f"{base}/ipset/{name}", {"cidr": cidr, **({"nomatch": 1} if nomatch else {})})
    return changes


def _describe(r):
    parts = [r["type"].upper(), r["action"]]
    for k in ("source", "dest", "proto", "dport"):
        if k in r:
            parts.append(f"{k}={r[k]}")
    if r.get("log", "nolog") != "nolog":
        parts.append(f"log={r['log']}")
    return " ".join(parts)


def sync_guest(api, node, kind, vmid, desired, apply):
    """Bringt einen Gast auf den Soll-Zustand; liefert die Aenderungen als Text."""
    base = f"/nodes/{node}/{kind}/{vmid}/firewall"
    # IP-Sets zuerst: Regeln duerfen nur auf vorhandene Sets verweisen
    changes = _sync_ipsets(api, base, desired["ipsets"], apply)

    current = sorted(api.get(f"{base}/rules"), key=lambda r: int(r["pos"]))
    if [normalize_rule(r) for r in current] != desired["rules"]:
        have = [_describe(normalize_rule(r)) for r in current]
        want = [_describe(r) for r in desired["rules"]]
        diff = [f"Regel weg: {d}" for d in have if d not in want] + [f"Regel neu: {d}" for d in want if d not in have]
        changes += diff or ["Regeln: neue Reihenfolge"]
        if apply:
            # Waehrend des Tauschs nie "Eingang zu, aber keine Regeln"
            if normalize_options(api.get(f"{base}/options"))["policy_in"] == "DROP":
                api.put(f"{base}/options", {"policy_in": "ACCEPT"})
            for r in reversed(current):
                api.delete(f"{base}/rules/{r['pos']}")
            # PVE setzt jede neue Regel ganz oben ein (pos wird beim Anlegen
            # ignoriert) - deshalb von hinten nach vorn anlegen
            for r in reversed(desired["rules"]):
                api.post(f"{base}/rules", r)
            # Gegenprobe: die Reihenfolge entscheidet, was greift
            written = sorted(api.get(f"{base}/rules"), key=lambda r: int(r["pos"]))
            if [normalize_rule(r) for r in written] != desired["rules"]:
                raise RuntimeError("Regel-Reihenfolge nach dem Schreiben falsch")

    cur = normalize_options(api.get(f"{base}/options"))
    diff = {k: v for k, v in desired["options"].items() if cur.get(k) != v}
    if diff:
        changes.append("Optionen: " + ", ".join(f"{k} {cur.get(k)} -> {v}" for k, v in diff.items()))
        if apply:
            api.put(f"{base}/options", diff)
    return changes


def run(api, policy, apply, only=None):
    resources = {int(r["vmid"]): r for r in api.get("/cluster/resources?type=vm")}
    rc = 0
    for name in sorted(policy["guests"]):
        if only and name not in only:
            continue
        g = policy["guests"][name]
        res = resources.get(g["vmid"])
        kind = g.get("kind", "lxc")
        if not res or res["type"] != kind:
            print(f"{name} ({kind} {g['vmid']}): nicht gefunden")
            rc = 1
            continue
        try:
            changes = sync_guest(api, res["node"], kind, g["vmid"], render_guest(policy, name), apply)
        except Exception as e:  # ein Gast darf die anderen nicht aufhalten
            print(f"{name}: FEHLER {e}")
            rc = 1
            continue
        print(f"{name} [{g['mode']}]: " + ("unveraendert" if not changes else f"{len(changes)} Aenderung(en)"))
        for c in changes:
            print(f"  {c}")
    return rc


class Api:
    def __init__(self, url, user, token_id, secret, cafile):
        self.base = url.rstrip("/") + "/api2/json"
        self.auth = f"PVEAPIToken={user}!{token_id}={secret}"
        self.ctx = ssl.create_default_context(cafile=cafile)

    def _call(self, method, path, data=None):
        body = urllib.parse.urlencode(data).encode() if data is not None else None
        req = urllib.request.Request(self.base + path, data=body, method=method,
                                     headers={"Authorization": self.auth})
        try:
            with urllib.request.urlopen(req, context=self.ctx, timeout=30) as resp:
                return json.load(resp).get("data")
        except urllib.error.HTTPError as e:
            detail = e.read()[:300].decode(errors="replace")
            raise RuntimeError(f"{method} {path}: HTTP {e.code} {detail}") from None

    def get(self, path):
        return self._call("GET", path)

    def post(self, path, data):
        return self._call("POST", path, data)

    def put(self, path, data):
        return self._call("PUT", path, data)

    def delete(self, path):
        return self._call("DELETE", path)


def main(argv=None):
    ap = argparse.ArgumentParser(description="Proxmox-Firewall pro Gast abgleichen")
    ap.add_argument("--policy", default=ROOT / "firewall/policy.yml")
    ap.add_argument("--apply", action="store_true", help="aendern statt nur anzeigen")
    ap.add_argument("--only", nargs="*", help="nur diese Gaeste")
    args = ap.parse_args(argv)
    env = os.environ
    api = Api(env["PROXMOX_URL"], env["PROXMOX_USER"], env["PROXMOX_TOKEN_ID"],
              env["PROXMOX_TOKEN_SECRET"], str(ROOT / "ansible/files/pve-root-ca.pem"))
    print("Firewall: " + ("anwenden" if args.apply else "Trockenlauf (nichts wird geaendert)"))
    return run(api, load_policy(args.policy), args.apply, args.only)


if __name__ == "__main__":
    sys.exit(main())
