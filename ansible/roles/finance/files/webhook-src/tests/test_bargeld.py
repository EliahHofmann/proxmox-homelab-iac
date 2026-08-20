import datetime

import bargeld


def test_zugang_ohne_beschreibung():
    assert bargeld.parse_bargeld("bargeld 50") == ("zugang", 50.0, "")


def test_zugang_mit_beschreibung():
    art, betrag, text = bargeld.parse_bargeld("bargeld 50 von Oma")
    assert (art, betrag, text) == ("zugang", 50.0, "von Oma")


def test_ausgabe_mit_komma():
    art, betrag, text = bargeld.parse_bargeld("bargeld ausgabe 12,50 Doener Imbiss")
    assert (art, betrag, text) == ("ausgabe", 12.5, "Doener Imbiss")


def test_ausgabe_gross_geschrieben():
    art, betrag, _ = bargeld.parse_bargeld("Bargeld Ausgabe 3.20 Kaffee")
    assert (art, betrag) == ("ausgabe", 3.2)


def test_ausgeschriebener_betrag_wird_abgelehnt():
    # "zwoelf euro" ist kein Betrag -> es darf nichts gebucht werden.
    assert bargeld.parse_bargeld("bargeld ausgabe zwoelf euro doener")[0] is None


def test_fehlender_betrag_wird_abgelehnt():
    assert bargeld.parse_bargeld("bargeld")[0] is None
    assert bargeld.parse_bargeld("bargeld ausgabe")[0] is None


def test_unplausibel_hoher_betrag_wird_abgelehnt():
    assert bargeld.parse_bargeld("bargeld 99999")[0] is None


def test_null_und_negativ_werden_abgelehnt():
    assert bargeld.parse_bargeld("bargeld 0")[0] is None
    assert bargeld.parse_bargeld("bargeld -5")[0] is None


def test_fremdes_kommando_wird_nicht_angefasst():
    assert bargeld.parse_bargeld("saldo")[0] is None


def test_hilfetext_zeigt_beide_formen():
    t = bargeld.hilfetext()
    assert "bargeld 50" in t
    assert "bargeld ausgabe" in t


def test_buchung_ausgabe_geht_vom_bargeldkonto_ab():
    p = bargeld.baue_buchung("ausgabe", 12.5, "Doener Imbiss", datetime.date(2026, 8, 20))
    t = p["transactions"][0]
    assert t["type"] == "withdrawal"
    assert t["source_name"] == "Bargeld"
    assert t["destination_name"] == bargeld.EXPENSE_BAR
    assert t["amount"] == "12.50"
    assert t["date"] == "2026-08-20"
    assert t["category_name"]          # ohne Kategorie taucht es im Bericht nicht auf


def test_buchung_zugang_kommt_aufs_bargeldkonto():
    p = bargeld.baue_buchung("zugang", 50.0, "von Oma", datetime.date(2026, 8, 20))
    t = p["transactions"][0]
    assert t["type"] == "deposit"
    assert t["destination_name"] == "Bargeld"
    assert t["source_name"] == bargeld.QUELLE_BAR


def test_bekannter_haendler_bekommt_seine_kategorie():
    p = bargeld.baue_buchung("ausgabe", 9.99, "Netto Einkauf")
    assert p["transactions"][0]["category_name"] == "Lebensmittel"


def test_unbekannte_beschreibung_wird_sonstiges():
    p = bargeld.baue_buchung("ausgabe", 5.0, "Flohmarkt")
    assert p["transactions"][0]["category_name"] == "Sonstiges"


def test_verarbeite_bucht_nicht_bei_unklarer_nachricht(monkeypatch):
    gebucht = []
    monkeypatch.setattr(bargeld, "buche", lambda *a, **k: gebucht.append(a))
    antwort = bargeld.verarbeite("bargeld ausgabe zwoelf euro", "http://x", "tok")
    assert gebucht == []
    assert "bargeld ausgabe" in antwort


def test_verarbeite_meldet_neuen_stand(monkeypatch):
    monkeypatch.setattr(bargeld, "buche", lambda *a, **k: {})
    monkeypatch.setattr(bargeld, "kontostand", lambda *a, **k: 37.5)
    antwort = bargeld.verarbeite("bargeld ausgabe 12,50 Doener", "http://x", "tok")
    assert "12.50" in antwort
    assert "37.50" in antwort


def test_stand_wird_erkannt():
    assert bargeld.parse_bargeld("bargeld stand 8") == ("stand", 8.0, "")
    assert bargeld.parse_bargeld("bargeld ist 8,50")[0] == "stand"


def test_stand_bucht_die_differenz_nach_unten(monkeypatch):
    gebucht = {}
    monkeypatch.setattr(bargeld, "kontostand", lambda *a, **k: 60.0)
    monkeypatch.setattr(bargeld, "buche", lambda base, tok, p: gebucht.update(p))
    antwort = bargeld.verarbeite("bargeld stand 8", "http://x", "tok")
    t = gebucht["transactions"][0]
    assert t["type"] == "withdrawal"
    assert t["amount"] == "52.00"
    assert "60.00 -> 8.00" in antwort


def test_stand_bucht_die_differenz_nach_oben(monkeypatch):
    gebucht = {}
    monkeypatch.setattr(bargeld, "kontostand", lambda *a, **k: 10.0)
    monkeypatch.setattr(bargeld, "buche", lambda base, tok, p: gebucht.update(p))
    bargeld.verarbeite("bargeld stand 25", "http://x", "tok")
    t = gebucht["transactions"][0]
    assert t["type"] == "deposit"
    assert t["amount"] == "15.00"


def test_stand_ohne_abweichung_bucht_nichts(monkeypatch):
    gebucht = []
    monkeypatch.setattr(bargeld, "kontostand", lambda *a, **k: 8.0)
    monkeypatch.setattr(bargeld, "buche", lambda *a, **k: gebucht.append(a))
    antwort = bargeld.verarbeite("bargeld stand 8", "http://x", "tok")
    assert gebucht == []
    assert "bereits" in antwort
