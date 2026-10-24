"""Tests fuer die Rolle ssh_access: Schluessel lesen, Aussperr-Schutz, Vorlagen.

Nur erfundene Beispielschluessel.
"""
import importlib.util
from pathlib import Path

import jinja2

ROLE = Path(__file__).resolve().parents[2] / "ansible/roles/ssh_access"
spec = importlib.util.spec_from_file_location("ssh_access_keys", ROLE / "filter_plugins/ssh_access_keys.py")
plugin = importlib.util.module_from_spec(spec)
spec.loader.exec_module(plugin)

OWNER = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIOwnerExampleKey0000000000000000000000000 owner"
PIPE = "ssh-ed25519 AAAAC3NzaC1lZDI1NTE5AAAAIPipelineExampleKey00000000000000000000000 pipeline"
PIPE_BODY = " ".join(PIPE.split()[:2])


def render(name, **ctx):
    # Wie Ansibles template-Modul: trim_blocks an
    env = jinja2.Environment(undefined=jinja2.StrictUndefined, keep_trailing_newline=True, trim_blocks=True)
    return env.from_string((ROLE / "templates" / name).read_text()).render(**ctx)


def test_schluessel_werden_normalisiert():
    raw = f"\r\n# Kommentar\n{OWNER}\r\n\n  {PIPE}  \n"
    keys = plugin.parse_keys(raw)
    assert [k["body"] for k in keys] == [" ".join(OWNER.split()[:2]), PIPE_BODY]
    assert keys[0]["comment"] == "owner"


def test_optionen_vor_dem_schluessel_werden_ignoriert():
    keys = plugin.parse_keys('from="192.0.2.1",no-pty ' + PIPE)
    assert keys[0]["body"] == PIPE_BODY


def test_doppelte_schluessel_nur_einmal():
    assert len(plugin.parse_keys(f"{OWNER}\n{OWNER}\n")) == 1


def test_gate_braucht_zwei_schluessel_und_den_eigenen():
    both = plugin.parse_keys(f"{OWNER}\n{PIPE}")
    assert plugin.keys_safe(both, PIPE_BODY)
    assert not plugin.keys_safe(plugin.parse_keys(PIPE), PIPE_BODY)      # nur einer
    assert not plugin.keys_safe(plugin.parse_keys(OWNER + "\n" + OWNER.replace("Owner", "Other")), PIPE_BODY)  # eigener fehlt
    assert not plugin.keys_safe(plugin.parse_keys(""), PIPE_BODY)
    assert not plugin.keys_safe(both, "")


def test_pipeline_zeile_nur_vom_runner():
    text = render("authorized_keys.j2", ssh_access_keys=plugin.parse_keys(f"{OWNER}\n{PIPE}"),
                  ssh_access_pipeline_body=PIPE_BODY, ssh_access_runner_ip="192.0.2.61")
    lines = [l for l in text.splitlines() if not l.startswith("#")]
    assert lines == [
        OWNER,
        'from="192.0.2.61",no-agent-forwarding,no-port-forwarding,no-X11-forwarding ' + PIPE,
    ]
    assert text.startswith("# Verwaltet von Ansible")


def test_sshd_nur_mit_schluessel():
    text = render("10-hardening.conf.j2")
    for line in ("PasswordAuthentication no", "KbdInteractiveAuthentication no",
                 "PermitRootLogin prohibit-password"):
        assert line in text.splitlines()
