"""Moves homelab alarm mails from the inbox into the alerts folder.

Alertmanager sends through the account's own Proton bridge, so Proton treats the
mails as sent by the user and its filters never touch them. This script does the
sorting instead; a systemd timer runs it every 2 minutes inside the Paperless
webserver container (it can reach proton-bridge on the compose network).

Credentials come on stdin, user on line 1 and password on line 2, so they never
show up in argv or the environment. The login only happens after STARTTLS and a
check of the bridge certificate's SHA-256 fingerprint (same pin as the alert SMTP).
"""
import argparse
import email
import hashlib
import imaplib
import ssl
import sys
from email.header import decode_header, make_header


def _betreff(raw):
    msg = email.message_from_bytes(raw)
    return str(make_header(decode_header(msg.get("Subject", ""))))


def sortiere(imap, praefix, ordner, trocken=False):
    """Move every inbox mail whose subject starts with praefix; returns the count.

    trocken=True only counts, with the inbox opened read-only.
    """
    imap.select("INBOX", readonly=trocken)
    typ, data = imap.uid("SEARCH", None, "SUBJECT", '"%s"' % praefix)
    uids = data[0].split() if typ == "OK" and data and data[0] else []
    if not uids:
        return 0

    # SEARCH matches anywhere in the subject; only the prefix counts. One FETCH
    # per mail, because servers order the UID item differently in the response.
    treffer = []
    for uid in (u.decode() for u in uids):
        typ, data = imap.uid("FETCH", uid, "(BODY.PEEK[HEADER.FIELDS (SUBJECT)])")
        teile = [item[1] for item in data or [] if isinstance(item, tuple)]
        if typ == "OK" and teile and _betreff(teile[0]).startswith(praefix):
            treffer.append(uid)
    if not treffer or trocken:
        return len(treffer)

    menge = ",".join(treffer)
    if "MOVE" in imap.capabilities:
        typ, data = imap.uid("MOVE", menge, '"%s"' % ordner)
    elif "UIDPLUS" in imap.capabilities:
        # Only UID EXPUNGE is limited to our mails; a plain EXPUNGE would also
        # wipe anything else flagged as deleted.
        typ, data = imap.uid("COPY", menge, '"%s"' % ordner)
        if typ == "OK":
            typ, data = imap.uid("STORE", menge, "+FLAGS.SILENT", r"(\Deleted)")
        if typ == "OK":
            typ, data = imap.uid("EXPUNGE", menge)
    else:
        # COPY without a scoped delete would add another copy on every run
        raise RuntimeError("Server kann weder MOVE noch UID EXPUNGE, nichts nach %s verschoben" % ordner)
    if typ != "OK":
        raise RuntimeError("Verschieben nach %s fehlgeschlagen: %r" % (ordner, data))
    return len(treffer)


def main(argv=None, stdin=sys.stdin, connect=imaplib.IMAP4):
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--host", default="proton-bridge")
    ap.add_argument("--port", type=int, default=143)
    ap.add_argument("--praefix", default="[homelab]")
    ap.add_argument("--ordner", default="Folders/Alerts")
    ap.add_argument("--fingerprint", required=True, help="SHA-256 des Bridge-Zertifikats")
    ap.add_argument("--trocken", action="store_true", help="nur zaehlen, nichts verschieben")
    args = ap.parse_args(argv)

    want = args.fingerprint.replace(":", "").strip().lower()
    zeilen = stdin.read().splitlines() + ["", ""]
    user, pw = zeilen[0].strip(), zeilen[1]
    if not want or not user or not pw:
        print("Fingerabdruck oder Zugangsdaten fehlen", file=sys.stderr)
        return 2

    # Self-signed bridge cert: the chain can't be verified, the pin below does it
    context = ssl.create_default_context()
    context.check_hostname = False
    context.verify_mode = ssl.CERT_NONE
    imap = connect(args.host, args.port)
    try:
        imap.starttls(ssl_context=context)
        der = imap.sock.getpeercert(binary_form=True) or b""
        if hashlib.sha256(der).hexdigest() != want:
            print("Bridge-Zertifikat passt nicht zum Fingerabdruck, kein Login", file=sys.stderr)
            return 3
        imap.login(user, pw)
        n = sortiere(imap, args.praefix, args.ordner, trocken=args.trocken)
    finally:
        try:
            imap.logout()
        except (imaplib.IMAP4.error, OSError):
            pass
    if n or args.trocken:
        print("%d Alarm-Mail(s) %s %s" % (n, "wuerden verschoben nach" if args.trocken else "verschoben nach", args.ordner))
    return 0


if __name__ == "__main__":
    sys.exit(main())
