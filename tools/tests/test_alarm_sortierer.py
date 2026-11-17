"""Tests fuer ansible/roles/paperless/files/alarm_sortierer.py (nur Beispielwerte)."""
import hashlib
import io
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "ansible" / "roles" / "paperless" / "files"))

import alarm_sortierer  # noqa: E402

CERT = b"bridge-cert"
FP = hashlib.sha256(CERT).hexdigest()


class FakeSock:
    def __init__(self, der):
        self.der = der

    def getpeercert(self, binary_form=False):
        return self.der


class FakeImap:
    """IMAP-Server im Speicher: uid -> Betreff, merkt sich alle Aufrufe."""

    def __init__(self, mails, move=True, ordner_fehlt=False, uidplus=False):
        self.mails = dict(mails)
        self.capabilities = ("IMAP4REV1",) + (("MOVE",) if move else ()) + (("UIDPLUS",) if uidplus else ())
        self.ordner_fehlt = ordner_fehlt
        self.calls = []
        self.logged_in = None
        self.sock = FakeSock(CERT)

    def starttls(self, ssl_context=None):
        self.calls.append(("starttls",))
        return "OK", [b""]

    def login(self, user, pw):
        self.calls.append(("login",))
        self.logged_in = (user, pw)
        return "OK", [b""]

    def select(self, mailbox, readonly=False):
        self.calls.append(("select", mailbox, readonly))
        return "OK", [str(len(self.mails)).encode()]

    def uid(self, cmd, *args):
        self.calls.append(("uid", cmd) + args)
        if cmd == "SEARCH":
            return "OK", [b" ".join(str(u).encode() for u in self.mails)]
        if cmd == "FETCH":
            data = []
            for u in args[0].split(","):
                subj = self.mails[int(u)]
                data.append((b"%s (UID %s BODY[HEADER.FIELDS (SUBJECT)] {1}" % (u.encode(), u.encode()),
                             b"Subject: " + subj.encode() + b"\r\n\r\n"))
                data.append(b")")
            return "OK", data
        if cmd in ("MOVE", "COPY"):
            if self.ordner_fehlt:
                return "NO", [b"no such mailbox"]
            return "OK", [b""]
        if cmd in ("STORE", "EXPUNGE"):
            return "OK", [b""]
        raise AssertionError(cmd)

    def expunge(self):
        self.calls.append(("expunge",))
        return "OK", [b""]

    def logout(self):
        return "BYE", [b""]


def moved(fake):
    return [c for c in fake.calls if c[0] == "uid" and c[1] in ("MOVE", "COPY")]


def test_nur_mails_mit_praefix_werden_verschoben():
    fake = FakeImap({1: "[homelab] ALARM: Beispiel", 2: "Re: wer hat [homelab] gesagt", 3: "[homelab] behoben: Beispiel"})
    n = alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts")
    assert n == 2
    assert moved(fake) == [("uid", "MOVE", "1,3", '"Folders/Alerts"')]


def test_kodierter_betreff_wird_erkannt():
    fake = FakeImap({7: "=?utf-8?q?=5Bhomelab=5D_Wochen-Digest?="})
    assert alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts") == 1


def test_ohne_move_copy_und_nur_die_eigenen_mails_loeschen():
    fake = FakeImap({4: "[homelab] ALARM: Beispiel"}, move=False, uidplus=True)
    assert alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts") == 1
    cmds = [c[:3] for c in fake.calls if c[0] in ("uid", "expunge")]
    assert cmds == [("uid", "SEARCH", None), ("uid", "FETCH", "4"), ("uid", "COPY", "4"),
                    ("uid", "STORE", "4"), ("uid", "EXPUNGE", "4")]


def test_ohne_move_und_uidplus_abbruch_statt_doppelter_kopien():
    # Ein normales EXPUNGE wuerde auch fremde, nur markierte Mails endgueltig loeschen,
    # COPY ohne Loeschen wuerde alle 2 Minuten eine weitere Kopie anlegen
    fake = FakeImap({4: "[homelab] ALARM: Beispiel"}, move=False, uidplus=False)
    try:
        alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts")
    except RuntimeError:
        pass
    else:
        raise AssertionError("kein Fehler")
    assert ("expunge",) not in fake.calls
    assert moved(fake) == []


def test_nichts_zu_tun_verschiebt_nichts():
    fake = FakeImap({})
    assert alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts") == 0
    assert moved(fake) == []


def test_posteingang_wird_schreibbar_geoeffnet():
    fake = FakeImap({1: "[homelab] ALARM: Beispiel"})
    alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts")
    assert fake.calls[0] == ("select", "INBOX", False)


def test_fehlender_zielordner_ist_fehler():
    fake = FakeImap({1: "[homelab] ALARM: Beispiel"}, ordner_fehlt=True)
    try:
        alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Gibtsnicht")
    except RuntimeError as e:
        assert "Folders/Gibtsnicht" in str(e)
    else:
        raise AssertionError("kein Fehler")


def test_zugangsdaten_kommen_von_stdin():
    fake = FakeImap({})
    rc = alarm_sortierer.main(["--host", "h", "--fingerprint", FP],
                              stdin=io.StringIO("user@example.org\ngeheim\n"), connect=lambda h, p: fake)
    assert rc == 0
    assert fake.logged_in == ("user@example.org", "geheim")
    assert fake.calls[:2] == [("starttls",), ("login",)]


def test_falsches_zertifikat_kein_login():
    fake = FakeImap({})
    fake.sock = FakeSock(b"fremdes-cert")
    rc = alarm_sortierer.main(["--fingerprint", FP], stdin=io.StringIO("u\np\n"), connect=lambda h, p: fake)
    assert rc == 3
    assert fake.logged_in is None


def test_ohne_fingerabdruck_keine_verbindung():
    def connect(h, p):
        raise AssertionError("darf nicht verbinden")
    assert alarm_sortierer.main(["--fingerprint", ""], stdin=io.StringIO("u\np\n"), connect=connect) == 2


def test_leere_zugangsdaten_brechen_ab_ohne_verbindung():
    def connect(h, p):
        raise AssertionError("darf nicht verbinden")
    assert alarm_sortierer.main(["--fingerprint", FP], stdin=io.StringIO("\n"), connect=connect) == 2


def test_trockenlauf_zaehlt_ohne_zu_verschieben():
    fake = FakeImap({1: "[homelab] ALARM: Beispiel", 2: "Hallo"})
    assert alarm_sortierer.sortiere(fake, "[homelab]", "Folders/Alerts", trocken=True) == 1
    assert moved(fake) == []
    assert fake.calls[0] == ("select", "INBOX", True)
