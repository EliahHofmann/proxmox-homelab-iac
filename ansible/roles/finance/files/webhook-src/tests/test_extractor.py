import datetime
from extractor import parse_ai_json, fit_text


def test_parse_valid():
    d = parse_ai_json('{"haendler":"Amazon","betrag_euro":19.99,"datum":"2026-07-05","kategorie":"Elektronik"}')
    assert d["haendler"] == "Amazon"
    assert d["betrag_euro"] == 19.99
    assert d["datum"] == "2026-07-05"
    assert d["kategorie"] == "Elektronik"


def test_parse_garbage_uses_defaults():
    d = parse_ai_json("kein json hier")
    assert d["haendler"] == "Unbekannt"
    assert d["betrag_euro"] == 0.0
    assert d["datum"] == datetime.date.today().isoformat()
    assert d["kategorie"] == "Sonstiges"


def test_parse_comma_amount():
    d = parse_ai_json('{"haendler":"X","betrag_euro":"19,99","datum":"2026-07-05","kategorie":"Y"}')
    assert d["betrag_euro"] == 19.99


def test_parse_negative_amount_becomes_positive():
    d = parse_ai_json('{"haendler":"X","betrag_euro":-42.50,"datum":"2026-07-05","kategorie":"Y"}')
    assert d["betrag_euro"] == 42.50


def test_parse_invalid_date_falls_back_to_today():
    d = parse_ai_json('{"haendler":"X","betrag_euro":1,"datum":"05.07.2026","kategorie":"Y"}')
    assert d["datum"] == datetime.date.today().isoformat()


def test_parse_euro_suffix_amount():
    d = parse_ai_json('{"haendler":"X","betrag_euro":"12.30 EUR","datum":"2026-07-05","kategorie":"Y"}')
    assert d["betrag_euro"] == 12.30


def test_gesamtbetrag_wird_verwendet():
    d = parse_ai_json('{"haendler":"Amazon","gesamtbetrag":24.63,"positionen":[12.99,8.49,3.15],"kategorie":"Online-Shopping"}')
    assert d["betrag_euro"] == 24.63


def test_positionen_werden_summiert_wenn_keine_gesamtsumme():
    d = parse_ai_json('{"haendler":"Amazon","gesamtbetrag":null,"positionen":[12.99,8.49,3.15]}')
    assert d["betrag_euro"] == 24.63


def test_gesamtbetrag_schlaegt_positionen():
    # Endsumme steht im Dokument -> Positionen werden ignoriert (kein Doppelzaehlen).
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":50.00,"positionen":[10,10,10]}')
    assert d["betrag_euro"] == 50.00


def test_positionen_als_komma_strings():
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":null,"positionen":["12,99","8,49 EUR","3,15"]}')
    assert d["betrag_euro"] == 24.63


def test_kein_betrag_bleibt_null():
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":null,"positionen":[]}')
    assert d["betrag_euro"] == 0.0


def test_versand_als_eigene_position():
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":null,"positionen":[19.99,4.99]}')
    assert d["betrag_euro"] == 24.98


def test_fit_text_kurz_bleibt_unveraendert():
    assert fit_text("kurzer text") == "kurzer text"


def test_fit_text_behaelt_ende():
    text = "A" * 6000 + "GESAMTSUMME 24,63 EUR"
    out = fit_text(text, limit=4000)
    assert "GESAMTSUMME 24,63 EUR" in out
    assert len(out) <= 4000 + 5


def test_fit_text_behaelt_anfang():
    text = "HAENDLER AMAZON" + "B" * 6000
    out = fit_text(text, limit=4000)
    assert "HAENDLER AMAZON" in out


def test_fit_text_leer():
    assert fit_text("") == ""
    assert fit_text(None) == ""
