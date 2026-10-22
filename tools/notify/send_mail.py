#!/usr/bin/env python3
"""Schickt eine Alarm-Mail ueber die Proton-Bridge (SMTP mit STARTTLS).

Zugangsdaten kommen aus der Umgebung (Pipeline, aus Vault) und fallen auf
eine Kopie auf dem Runner zurueck (~/.alert-smtp, 0600). So geht die Mail
auch raus, wenn Vault versiegelt ist und die Pipeline deshalb scheitert.

Exit: 0 gesendet, 2 Konfiguration fehlt, 3 Versand fehlgeschlagen.
"""
import argparse
import smtplib
import ssl
import sys
from dataclasses import dataclass
from email.message import EmailMessage
from pathlib import Path
from typing import Mapping

KEYS = ("ALERT_SMTP_HOST", "ALERT_SMTP_PORT", "ALERT_SMTP_USER",
        "ALERT_SMTP_PASSWORD", "ALERT_MAIL_TO")
DEFAULT_CACHE = Path.home() / ".alert-smtp"


class ConfigError(Exception):
    pass


@dataclass(frozen=True)
class SmtpConfig:
    host: str
    port: int
    user: str
    password: str
    mail_to: str


def _read_cache(cache_file: Path) -> dict:
    values = {}
    if cache_file.is_file():
        for line in cache_file.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line or line.startswith("#") or "=" not in line:
                continue
            key, value = line.split("=", 1)
            values[key.strip()] = value.strip()
    return values


def load_config(environ: Mapping[str, str], cache_file: Path) -> SmtpConfig:
    cached = _read_cache(cache_file)
    values = []
    for key in KEYS:
        value = environ.get(key) or cached.get(key)
        if not value:
            raise ConfigError(key)
        values.append(value)
    host, port, user, password, mail_to = values
    return SmtpConfig(host, int(port), user, password, mail_to)


def send(cfg: SmtpConfig, subject: str, body: str, smtp_factory=smtplib.SMTP) -> None:
    msg = EmailMessage()
    msg["From"] = cfg.user
    msg["To"] = cfg.mail_to
    msg["Subject"] = f"[homelab] {subject}"
    msg.set_content(body)
    # Die Bridge nutzt ein selbstsigniertes Zertifikat, Verbindung nur im LAN.
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    with smtp_factory(cfg.host, cfg.port, timeout=30) as smtp:
        smtp.starttls(context=context)
        smtp.login(cfg.user, cfg.password)
        smtp.send_message(msg)


def main(argv=None, smtp_factory=smtplib.SMTP) -> int:
    import os

    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--subject", required=True)
    body = parser.add_mutually_exclusive_group(required=True)
    body.add_argument("--body")
    body.add_argument("--body-file", type=Path)
    parser.add_argument("--cache-file", type=Path, default=DEFAULT_CACHE)
    args = parser.parse_args(argv)

    try:
        cfg = load_config(os.environ, args.cache_file)
    except ConfigError as e:
        print(f"missing {e}", file=sys.stderr)
        return 2
    text = args.body if args.body is not None else args.body_file.read_text(encoding="utf-8")
    try:
        send(cfg, args.subject, text, smtp_factory=smtp_factory)
    except Exception as e:  # jeder Fehler soll im Job-Log lesbar landen
        print(f"send failed: {type(e).__name__}: {e}", file=sys.stderr)
        return 3
    print(f"sent to {cfg.mail_to}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
