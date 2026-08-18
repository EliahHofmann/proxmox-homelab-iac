import datetime
from extractor import parse_ai_json, fit_text, datum_aus_text, SYSTEM_PROMPT


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


def test_mehrere_rechnungen_werden_summiert():
    # Ein PDF kann mehrere Rechnungen enthalten (mehrere Verkaeufer, je eigener
    # Gesamtpreis). Abgebucht wird die Summe - nur so findet das matching_job
    # die passende Bankbuchung.
    d = parse_ai_json('{"haendler":"Shop","gesamtbetrag":null,"positionen":[10.00,20.00],'
                      '"datum":"2020-03-15","kategorie":"Online-Shopping"}')
    assert d["betrag_euro"] == 30.00
    assert d["datum"] == "2020-03-15"


def test_prompt_nennt_regel_fuer_mehrere_rechnungen():
    assert "MEHRERE Rechnungen" in SYSTEM_PROMPT


def test_prompt_nennt_datumsumrechnung():
    # Ohne diese Regel liefert das Modell das Beispieldatum oder das heutige Datum.
    assert "TT.MM.JJJJ" in SYSTEM_PROMPT
    assert "Nimm nicht das heutige Datum." in SYSTEM_PROMPT


def test_datum_aus_text_findet_rechnungsdatum():
    text = "Rechnungsdatum /Lieferdatum 10.07.2020  Bestelldatum 08.07.2020"
    assert datum_aus_text(text) == "2020-07-10"


def test_datum_aus_text_ueberspringt_unmoegliches_datum():
    assert datum_aus_text("Beleg 32.13.2020 vom 05.11.2020") == "2020-11-05"


def test_datum_aus_text_ohne_treffer():
    assert datum_aus_text("kein Datum enthalten") is None
    assert datum_aus_text("") is None
    assert datum_aus_text(None) is None


def test_unmoegliches_ki_datum_faellt_auf_beleg_zurueck():
    # Beobachtet: das Modell lieferte "2025-16-00". Ohne Fallback wuerde heute
    # gesetzt und das matching_job faende die Bankbuchung (+-7 Tage) nicht mehr.
    d = parse_ai_json('{"haendler":"Shop","gesamtbetrag":50.00,"datum":"2025-16-00"}',
                      ocr_text="Rechnungsdatum 14.05.2020")
    assert d["datum"] == "2020-05-14"
    assert d["betrag_euro"] == 50.00


def test_gueltiges_ki_datum_schlaegt_den_fallback():
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":10,"datum":"2020-07-10"}',
                      ocr_text="Rechnungsdatum 14.05.2020")
    assert d["datum"] == "2020-07-10"


def test_ohne_ocr_text_bleibt_es_beim_heutigen_datum():
    d = parse_ai_json('{"haendler":"X","gesamtbetrag":10,"datum":"2025-16-00"}')
    assert d["datum"] == datetime.date.today().isoformat()
