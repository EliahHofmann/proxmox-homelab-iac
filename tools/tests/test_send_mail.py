"""Tests fuer tools/notify/send_mail.py (nur Beispielwerte, keine echten Daten)."""
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notify"))

import send_mail  # noqa: E402

FULL_FILE = (
    "# Kopie aus Vault, Fallback bei versiegeltem Vault\n"
    "ALERT_SMTP_HOST=filehost\n"
    "ALERT_SMTP_PORT=1025\n"
    "ALERT_SMTP_USER=u\n"
    "ALERT_SMTP_PASSWORD=p\n"
    "ALERT_MAIL_TO=to@example.org\n"
)


class FakeSMTP:
    """Zeichnet die Aufrufe auf, statt zu verbinden."""

    instances = []

    def __init__(self, host, port, timeout=None):
        self.calls = []
        self.messages = []
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append("send")
        self.messages.append(msg)


def write_cache(tmp_path, text=FULL_FILE):
    f = tmp_path / "alert-smtp"
    f.write_text(text, encoding="utf-8")
    return f


def test_env_wins_over_cache_file(tmp_path):
    cfg = send_mail.load_config({"ALERT_SMTP_HOST": "envhost"}, write_cache(tmp_path))
    assert cfg.host == "envhost"
    assert cfg.user == "u"
    assert cfg.mail_to == "to@example.org"


def test_cache_file_used_when_env_empty(tmp_path):
    cfg = send_mail.load_config({}, write_cache(tmp_path))
    assert cfg == send_mail.SmtpConfig("filehost", 1025, "u", "p", "to@example.org")
    assert isinstance(cfg.port, int)


def test_missing_key_raises(tmp_path):
    text = "\n".join(l for l in FULL_FILE.splitlines() if not l.startswith("ALERT_MAIL_TO"))
    with pytest.raises(send_mail.ConfigError, match="ALERT_MAIL_TO"):
        send_mail.load_config({}, write_cache(tmp_path, text))


def test_send_uses_starttls_login_and_prefix():
    FakeSMTP.instances.clear()
    cfg = send_mail.SmtpConfig("h", 1025, "u", "p", "to@example.org")
    send_mail.send(cfg, "Deploy rot", "body", smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[0]
    assert smtp.calls == ["starttls", ("login", "u", "p"), "send"]
    msg = smtp.messages[0]
    assert msg["Subject"] == "[homelab] Deploy rot"
    assert msg["To"] == "to@example.org"


def test_cli_send_failure_exit_3_without_password(tmp_path, monkeypatch, capsys):
    def refusing(*a, **kw):
        raise ConnectionRefusedError("connection refused")

    for key in ("ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER",
                "ALERT_SMTP_PASSWORD", "ALERT_MAIL_TO"):
        monkeypatch.delenv(key, raising=False)
    cache = write_cache(tmp_path, FULL_FILE.replace("=p\n", "=secret-pw\n"))
    rc = send_mail.main(
        ["--subject", "x", "--body", "y", "--cache-file", str(cache)], smtp_factory=refusing
    )
    out = capsys.readouterr()
    assert rc == 3
    assert "send failed: ConnectionRefusedError" in out.out + out.err
    assert "secret-pw" not in out.out + out.err
