import datetime

import pytest

from umbuchung import WEGE, parse_betrag, parse_datum, baue_transfer, weg_aufloesen


def test_parse_betrag_punkt_und_komma():
    assert parse_betrag("500") == 500.0
    assert parse_betrag("12,50") == 12.5
    assert parse_betrag("12.50") == 12.5
    assert parse_betrag("1.234,56") == 1234.56


def test_parse_betrag_mit_euro_zeichen():
    assert parse_betrag("99,99 EUR") == 99.99
    assert parse_betrag("50 €") == 50.0


def test_parse_betrag_lehnt_null_und_negativ_ab():
    for schrott in ("0", "-5", "abc", ""):
        with pytest.raises(ValueError):
            parse_betrag(schrott)


def test_parse_datum_leer_ist_heute():
    assert parse_datum("", heute=datetime.date(2026, 8, 5)) == "2026-08-05"
    assert parse_datum(None, heute=datetime.date(2026, 8, 5)) == "2026-08-05"


def test_parse_datum_deutsches_format():
    assert parse_datum("05.08.2026") == "2026-08-05"
    assert parse_datum("5.8.2026") == "2026-08-05"


def test_parse_datum_iso_bleibt():
    assert parse_datum("2026-08-05") == "2026-08-05"


def test_parse_datum_unbekanntes_format_wirft():
    with pytest.raises(ValueError):
        parse_datum("naechsten Montag")


def test_wege_sind_vollstaendig():
    """Die vier Wege, die der Nutzer regelmaessig geht."""
    assert set(WEGE) == {"sparen", "urlaub", "ibkr", "kraken", "zurueck"}


def test_weg_aufloesen_kennt_richtung():
    assert weg_aufloesen("sparen") == ("Sparkasse Giro", "Investment Sparkonto (C24)")
    assert weg_aufloesen("ibkr") == ("Investment Sparkonto (C24)", "IBKR Depot")


def test_weg_aufloesen_ist_case_insensitive():
    assert weg_aufloesen("IBKR") == weg_aufloesen("ibkr")


def test_weg_aufloesen_unbekannt_wirft_mit_hinweis():
    with pytest.raises(ValueError) as e:
        weg_aufloesen("tagesgeld")
    assert "sparen" in str(e.value)      # Fehlermeldung listet die gueltigen Wege


def test_baue_transfer_grundgeruest():
    t = baue_transfer("ibkr", 400.0, "2026-08-05")["transactions"][0]
    assert t["type"] == "transfer"
    assert t["amount"] == "400.00"
    assert t["source_name"] == "Investment Sparkonto (C24)"
    assert t["destination_name"] == "IBKR Depot"
    assert t["date"] == "2026-08-05"


def test_baue_transfer_setzt_tag_zur_nachverfolgung():
    """C24 laeuft nicht ueber den Bank-Import - manuelle Buchungen muessen erkennbar sein."""
    t = baue_transfer("sparen", 100.0, "2026-08-05")["transactions"][0]
    assert "manuell" in t["tags"]


def test_baue_transfer_eigene_notiz():
    t = baue_transfer("kraken", 50.0, "2026-08-05", notiz="Sparplan August")["transactions"][0]
    assert t["notes"] == "Sparplan August"


def test_baue_transfer_ohne_notiz_hat_standardtext():
    t = baue_transfer("urlaub", 50.0, "2026-08-05")["transactions"][0]
    assert t["notes"]


def test_baue_transfer_keine_regeln_anwenden():
    """Transfers brauchen keine Kategorie - Regeln wuerden nur stoeren."""
    assert baue_transfer("sparen", 10.0, "2026-08-05")["apply_rules"] is False


def test_baue_transfer_verhindert_doppelbuchung():
    assert baue_transfer("sparen", 10.0, "2026-08-05")["error_if_duplicate_hash"] is True
