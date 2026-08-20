import datetime

import kommando


def test_normalisiert_gross_klein_und_leerzeichen():
    assert kommando.parse_kommando("  Bericht \n") == "bericht"
    assert kommando.parse_kommando("SALDO") == "saldo"


def test_unbekanntes_kommando_wird_zu_hilfe():
    assert kommando.parse_kommando("wie geht es dir") == "hilfe"
    assert kommando.parse_kommando("") == "hilfe"
    assert kommando.parse_kommando(None) == "hilfe"


def test_erstes_wort_zaehlt():
    # ntfy haengt manchmal Zusatztext an - das erste Wort entscheidet.
    assert kommando.parse_kommando("bericht bitte") == "bericht"


def test_monat_bis_heute():
    start, end = kommando.monat_bis_heute(datetime.date(2026, 8, 19))
    assert start == "2026-08-01"
    assert end == "2026-08-19"


def test_monat_bis_heute_am_ersten():
    start, end = kommando.monat_bis_heute(datetime.date(2026, 8, 1))
    assert start == end == "2026-08-01"


def test_hilfe_nennt_alle_kommandos():
    text = kommando.formatiere_hilfe()
    for k in kommando.KOMMANDOS:
        assert k in text


def test_formatiere_bericht_rechnet_selbst():
    # Die KI formuliert nur - die Summe entsteht hier.
    text = kommando.formatiere_bericht({"Lebensmittel": 80.0, "Restaurant": 20.0},
                                       "2026-08-01", "2026-08-19")
    assert "100.00" in text
    assert "Lebensmittel" in text


def test_formatiere_bericht_ohne_ausgaben():
    text = kommando.formatiere_bericht({}, "2026-08-01", "2026-08-19")
    assert "keine ausgaben" in text.lower()


def test_formatiere_saldo_summiert_und_sortiert():
    text = kommando.formatiere_saldo([("Giro", 487.46), ("Bargeld", 0.0), ("Depot", 1674.99)])
    assert "2162.45" in text          # Summe
    assert text.index("Depot") < text.index("Giro")   # groesster zuerst


def test_formatiere_top_kuerzt_auf_fuenf():
    posten = [("2026-08-0%d" % (i + 1), f"Haendler {i}", float(100 - i), "") for i in range(8)]
    text = kommando.formatiere_top(posten)
    assert "Haendler 0" in text
    assert "Haendler 5" not in text


def test_formatiere_top_zeigt_datum_und_kategorie():
    text = kommando.formatiere_top([("2026-08-19", "AMZNPrime DE", 4.49, "Abos & Software")])
    assert "19.08." in text
    assert "[Abos & Software]" in text


def test_saubere_beschreibung_entfernt_transaktionsnummern():
    roh = "K01-111-222 AMZNPrime DE XY12AB34"
    assert kommando.saubere_beschreibung(roh) == "AMZNPrime DE"


def test_saubere_beschreibung_behaelt_haendler_bei_paypal():
    roh = "9999 PP.1000.PP . Spotify AB, Ihr Einkauf bei Spotify AB"
    assert kommando.saubere_beschreibung(roh).startswith("Spotify AB")


def test_saubere_beschreibung_faellt_auf_zielkonto_zurueck():
    # Bleibt nach dem Aussieben nichts uebrig, hilft der Name des Zielkontos.
    assert kommando.saubere_beschreibung("00001111 BLZ12345678", "Bargeldautomat") == "Bargeldautomat"


def test_saubere_beschreibung_ohne_alles():
    assert kommando.saubere_beschreibung("", "") == "ohne Bezeichnung"


def test_parse_accounts_nimmt_nur_aktive_assets():
    payload = {"data": [
        {"attributes": {"name": "Giro", "type": "asset", "active": True,
                        "current_balance": "487.46"}},
        {"attributes": {"name": "ALT Konto", "type": "asset", "active": False,
                        "current_balance": "10.00"}},
        {"attributes": {"name": "Ausgabekonto", "type": "expense", "active": True,
                        "current_balance": "5.00"}},
    ]}
    konten = kommando.parse_accounts(payload)
    assert konten == [("Giro", 487.46)]


def test_parse_transactions_liest_betrag_und_beschreibung():
    payload = {"data": [
        {"attributes": {"transactions": [
            {"amount": "44.99", "description": "Zelt", "type": "withdrawal"}]}},
        {"attributes": {"transactions": [
            {"amount": "12.50", "description": "Kaffee", "type": "withdrawal"},
            {"amount": "99.00", "description": "Umbuchung", "type": "transfer"}]}},
    ]}
    posten = kommando.parse_transactions(payload)
    assert posten == [("", "Zelt", 44.99, ""), ("", "Kaffee", 12.5, "")]   # Transfer faellt raus


def test_beantworte_nimmt_einen_abweichenden_zeitraum(monkeypatch):
    # Ohne Durchreichen wuerde "letzten Monat" still zum laufenden Monat.
    gesehen = {}

    def fake_fetch(base, pat, start, ende):
        gesehen["zeitraum"] = (start, ende)
        return {}

    monkeypatch.setattr(kommando, "fetch_expenses", fake_fetch)
    kommando.beantworte("bericht", "http://x", "tok", zeitraum=("2026-07-01", "2026-07-31"))
    assert gesehen["zeitraum"] == ("2026-07-01", "2026-07-31")


def test_top5_nennt_den_zeitraum():
    # Ohne Zeitraum stand "diesen Monat" auch ueber Vormonatszahlen.
    text = kommando.formatiere_top([("2026-07-21", "Etwas", 170.0, "")],
                                   start="2026-07-01", ende="2026-07-31")
    assert "2026-07-01 bis 2026-07-31" in text
    assert "diesen Monat" not in text


def test_top5_ohne_zeitraum_bleibt_lesbar():
    text = kommando.formatiere_top([("2026-08-19", "Etwas", 10.0, "")])
    assert "Groesste 5 Ausgaben:" in text


def test_sparquote_nennt_den_zeitraum():
    text = kommando.formatiere_sparquote(1000.0, 400.0, "2026-07-01", "2026-07-31")
    assert "2026-07-01 bis 2026-07-31" in text
    assert "diesen Monat" not in text
