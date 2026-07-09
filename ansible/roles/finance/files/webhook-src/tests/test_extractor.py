import datetime
from extractor import parse_ai_json


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
