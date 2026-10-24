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
    blocking = [r for r in rules(g, "out") if r.get("dest") in ("+owner", "192.168.178.10,192.168.178.11") and "dport" not in r]
    assert len(blocking) == 2 and all(r.get("log") == "info" for r in blocking)


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
    assert not any(r["action"] == "ACCEPT" and r.get("dest") == "192.168.178.10,192.168.178.11" for r in out)


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


class FakeApi:
    """Proxmox-API im Speicher.

    Wie PVE 9.2 (live beobachtet 2026-10-24): POST auf rules setzt die neue
    Regel immer ganz oben ein, ein mitgeschicktes pos wird ignoriert.
    """

    def __init__(self, guests):
        self.guests = guests                      # vmid -> (node, kind)
        self.fw = {v: {"options": {}, "rules": [], "ipsets": {}} for v in guests}
        self.writes = []

    def _guest(self, path):
        parts = path.strip("/").split("/")        # nodes/<n>/<kind>/<vmid>/firewall/...
        return self.fw[int(parts[3])], parts[5:]

    def get(self, path):
        if path.startswith("/cluster/resources"):
            return [{"vmid": v, "node": n, "type": k} for v, (n, k) in self.guests.items()]
        g, rest = self._guest(path)
        if rest == ["options"]:
            return dict(g["options"])
        if rest == ["rules"]:
            return [dict(r, pos=i, digest="x", ipversion=4) for i, r in enumerate(g["rules"])]
        if rest == ["ipset"]:
            return [{"name": n} for n in g["ipsets"]]
        if rest[0] == "ipset":
            return [dict(e) for e in g["ipsets"][rest[1]]]
        raise KeyError(path)

    def _write(self, op, path, data=None):
        self.writes.append((op, path, dict(data or {})))
        g, rest = self._guest(path)
        return g, rest

    def put(self, path, data):
        g, rest = self._write("PUT", path, data)
        g["options"].update(data)

    def post(self, path, data):
        g, rest = self._write("POST", path, data)
        if rest == ["rules"]:
            d = dict(data)
            d.pop("pos", None)
            g["rules"].insert(0, d)
        elif rest == ["ipset"]:
            g["ipsets"][data["name"]] = []
        else:
            e = {"cidr": data["cidr"]}
            if data.get("nomatch"):
                e["nomatch"] = 1
            g["ipsets"][rest[1]].append(e)

    def delete(self, path):
        g, rest = self._write("DELETE", path)
        if rest[0] == "rules":
            del g["rules"][int(rest[1])]
        else:
            g["ipsets"][rest[1]] = [e for e in g["ipsets"][rest[1]] if e["cidr"] != fw.unquote(rest[2])]


BASE = "/nodes/n1/lxc/205/firewall"


def synced(desired, apply=True):
    api = FakeApi({205: ("n1", "lxc")})
    fw.sync_guest(api, "n1", "lxc", 205, desired, apply=apply)
    return api


def test_abgleich_setzt_alles_in_richtiger_reihenfolge():
    desired = fw.render_guest(POLICY, "qwen3")
    api = synced(desired)
    stored = api.fw[205]
    assert [fw.normalize_rule(r) for r in stored["rules"]] == desired["rules"]
    assert fw.normalize_options(stored["options"]) == desired["options"]
    assert {(e["cidr"], bool(e.get("nomatch"))) for e in stored["ipsets"]["owner"]} == set(desired["ipsets"]["owner"])
    # IP-Sets vor den Regeln, die sie benutzen
    first_rule = next(i for i, w in enumerate(api.writes) if w[1].endswith("/rules"))
    assert all(not w[1].startswith(BASE + "/rules") for w in api.writes[:first_rule])
    assert any(w[1] == BASE + "/ipset" for w in api.writes[:first_rule])


def test_zweiter_lauf_aendert_nichts():
    desired = fw.render_guest(POLICY, "qwen3")
    api = synced(desired)
    api.writes.clear()
    changes = fw.sync_guest(api, "n1", "lxc", 205, desired, apply=True)
    assert changes == [] and api.writes == []


def test_trockenlauf_schreibt_nichts():
    api = FakeApi({205: ("n1", "lxc")})
    changes = fw.sync_guest(api, "n1", "lxc", 205, fw.render_guest(POLICY, "qwen3"), apply=False)
    assert changes and api.writes == []


def test_scharfer_gast_ist_beim_regeltausch_nie_ohne_regeln_zu():
    on = fw.render_guest(policy(qwen3="enforce"), "qwen3")
    api = synced(on)
    api.writes.clear()
    changed = copy.deepcopy(on)
    changed["rules"].insert(0, {"type": "in", "action": "ACCEPT", "source": "+owner", "proto": "tcp",
                                "dport": "1", "log": "nolog", "enable": 1, "comment": "neu"})
    fw.sync_guest(api, "n1", "lxc", 205, changed, apply=True)
    ops = api.writes
    first_delete = next(i for i, w in enumerate(ops) if w[0] == "DELETE")
    assert ops[first_delete - 1] == ("PUT", BASE + "/options", {"policy_in": "ACCEPT"})
    assert ops[-1][0] == "PUT" and ops[-1][2]["policy_in"] == "DROP"
    assert [fw.normalize_rule(r) for r in api.fw[205]["rules"]] == changed["rules"]


def test_ipset_eintraege_werden_ersetzt():
    desired = fw.render_guest(POLICY, "qwen3")
    api = synced(desired)
    api.fw[205]["ipsets"]["owner"].append({"cidr": "192.168.178.250", "nomatch": 1})
    api.writes.clear()
    fw.sync_guest(api, "n1", "lxc", 205, desired, apply=True)
    assert {(e["cidr"], bool(e.get("nomatch"))) for e in api.fw[205]["ipsets"]["owner"]} == set(desired["ipsets"]["owner"])
    assert not any(w[1].endswith("/rules") for w in api.writes)


def test_fehlender_gast_meldet_fehler_und_rest_laeuft(capsys):
    api = FakeApi({205: ("n1", "lxc")})
    rc = fw.run(api, policy(), apply=True)
    assert rc == 1
    assert "nicht gefunden" in capsys.readouterr().out
    assert api.fw[205]["rules"]


class AppendingApi(FakeApi):
    """Eine API, die neue Regeln unten anhaengt - anders als PVE."""

    def post(self, path, data):
        g, rest = self._guest(path)
        if rest == ["rules"]:
            self.writes.append(("POST", path, dict(data)))
            g["rules"].append({k: v for k, v in data.items() if k != "pos"})
        else:
            super().post(path, data)


def test_falsche_reihenfolge_nach_dem_schreiben_faellt_auf():
    api = AppendingApi({205: ("n1", "lxc")})
    with pytest.raises(RuntimeError, match="Reihenfolge"):
        fw.sync_guest(api, "n1", "lxc", 205, fw.render_guest(POLICY, "qwen3"), apply=True)


def test_gaeste_erreichen_den_tailscale_router():
    # .33 steht im owner-Set (reicht Besitzer-Geraete durch); die Sperre
    # "keine Besitzer-Geraete" darf ihn als Ziel trotzdem nicht treffen,
    # sonst kommen Monitoring (9100) und Runner (SSH) nicht mehr hin
    for name in ("monitoring", "runner", "paperless"):
        out = rules(fw.render_guest(policy(**{name: "enforce"}), name), "out")
        owner_drop = next(i for i, r in enumerate(out) if r.get("dest") == "+owner")
        proxy = [i for i, r in enumerate(out) if r["action"] == "ACCEPT" and r.get("dest") == "192.168.178.33"]
        assert proxy and proxy[0] < owner_drop, name
