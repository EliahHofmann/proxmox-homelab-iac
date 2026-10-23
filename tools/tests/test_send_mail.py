"""Tests fuer tools/notify/send_mail.py (nur Beispielwerte, keine echten Daten)."""
import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "notify"))

import send_mail  # noqa: E402

GOOD_FP = hashlib.sha256(b"bridge-cert").hexdigest()
FULL_FILE = (
    "# Kopie aus Vault, Fallback bei versiegeltem Vault\n"
    "ALERT_SMTP_HOST=filehost\n"
    "ALERT_SMTP_PORT=1025\n"
    "ALERT_SMTP_USER=u\n"
    "ALERT_SMTP_PASSWORD=p\n"
    "ALERT_MAIL_TO=to@example.org\n"
    f"ALERT_SMTP_FINGERPRINT={GOOD_FP}\n"
)


class FakeSock:
    def __init__(self, der):
        self.der = der

    def getpeercert(self, binary_form=False):
        return self.der


class FakeSMTP:
    """Zeichnet die Aufrufe auf, statt zu verbinden."""

    instances = []
    peer_der = b"bridge-cert"

    def __init__(self, host, port, timeout=None):
        self.calls = []
        self.messages = []
        self.sock = None
        FakeSMTP.instances.append(self)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def starttls(self, context=None):
        self.calls.append("starttls")
        self.sock = FakeSock(FakeSMTP.peer_der)

    def login(self, user, password):
        self.calls.append(("login", user, password))

    def send_message(self, msg):
        self.calls.append("send")
        self.messages.append(msg)


@pytest.fixture(autouse=True)
def reset_fake():
    FakeSMTP.instances.clear()
    FakeSMTP.peer_der = b"bridge-cert"


@pytest.fixture
def clean_env(monkeypatch):
    for key in send_mail.KEYS:
        monkeypatch.delenv(key, raising=False)


def write_cache(tmp_path, text=FULL_FILE):
    f = tmp_path / "alert-smtp"
    f.write_text(text, encoding="utf-8")
    return f


def cfg(fp=GOOD_FP):
    return send_mail.SmtpConfig("h", 1025, "u", "p", "to@example.org", fp)


def test_env_wins_over_cache_file(tmp_path):
    c = send_mail.load_config({"ALERT_SMTP_HOST": "envhost"}, write_cache(tmp_path))
    assert c.host == "envhost"
    assert c.user == "u"
    assert c.mail_to == "to@example.org"


def test_cache_file_used_when_env_empty(tmp_path):
    c = send_mail.load_config({}, write_cache(tmp_path))
    assert c == send_mail.SmtpConfig("filehost", 1025, "u", "p", "to@example.org", GOOD_FP)
    assert isinstance(c.port, int)


def test_missing_key_raises(tmp_path):
    text = "\n".join(l for l in FULL_FILE.splitlines() if not l.startswith("ALERT_MAIL_TO"))
    with pytest.raises(send_mail.ConfigError, match="ALERT_MAIL_TO"):
        send_mail.load_config({}, write_cache(tmp_path, text))


def test_send_uses_starttls_login_and_prefix():
    send_mail.send(cfg(), "Deploy rot", "body", smtp_factory=FakeSMTP)
    smtp = FakeSMTP.instances[0]
    assert smtp.calls == ["starttls", ("login", "u", "p"), "send"]
    msg = smtp.messages[0]
    assert msg["Subject"] == "[homelab] Deploy rot"
    assert msg["To"] == "to@example.org"


def test_fingerprint_mismatch_aborts_before_login():
    FakeSMTP.peer_der = b"attacker-cert"
    with pytest.raises(send_mail.FingerprintError):
        send_mail.send(cfg(), "x", "y", smtp_factory=FakeSMTP)
    assert FakeSMTP.instances[0].calls == ["starttls"]


def test_fingerprint_accepts_colon_notation():
    colon = ":".join(GOOD_FP[i:i + 2] for i in range(0, 64, 2)).upper()
    send_mail.send(cfg(colon), "x", "y", smtp_factory=FakeSMTP)
    assert "send" in FakeSMTP.instances[0].calls


def test_cli_send_failure_exit_3_without_details(tmp_path, clean_env, capsys):
    def refusing(*a, **kw):
        raise ConnectionRefusedError("connection refused")

    cache = write_cache(tmp_path, FULL_FILE.replace("=p\n", "=secret-pw\n"))
    rc = send_mail.main(
        ["--subject", "x", "--body", "y", "--cache-file", str(cache)], smtp_factory=refusing
    )
    out = capsys.readouterr()
    assert rc == 3
    assert "send failed: ConnectionRefusedError" in out.out + out.err
    assert "secret-pw" not in out.out + out.err
    assert "connection refused" not in out.out + out.err


def test_cli_output_never_shows_recipient(tmp_path, clean_env, capsys):
    # Pipeline-Logs sind oeffentlich (Repo public)
    rc = send_mail.main(
        ["--subject", "x", "--body", "y", "--cache-file", str(write_cache(tmp_path))],
        smtp_factory=FakeSMTP,
    )
    out = capsys.readouterr()
    assert rc == 0
    assert "example.org" not in out.out + out.err


def test_standard_cache_haengt_nicht_an_home(monkeypatch):
    # Der Runner-Dienst hat kein HOME; Schreiber (Action) und Leser muessen
    # trotzdem dieselbe Datei meinen.
    import importlib
    monkeypatch.setenv("HOME", "")
    neu = importlib.reload(send_mail)
    assert neu.DEFAULT_CACHE == Path("/home/github-runner/.alert-smtp")
