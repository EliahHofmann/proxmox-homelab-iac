import frage

KATEGORIEN = ["Lebensmittel", "Restaurant", "Online-Shopping"]


def test_auswahl_kategorie():
    roh = '{"funktion":"kategorie","kategorie":"Lebensmittel","zeitraum":"monat"}'
    assert frage.parse_auswahl(roh, KATEGORIEN) == ("kategorie", "Lebensmittel", "monat")


def test_kategorie_wird_unabhaengig_von_gross_klein_erkannt():
    roh = '{"funktion":"kategorie","kategorie":"lebensmittel"}'
    assert frage.parse_auswahl(roh, KATEGORIEN)[1] == "Lebensmittel"


def test_erfundene_kategorie_wird_verworfen():
    # Das Modell darf sich keine Kategorie ausdenken.
    roh = '{"funktion":"kategorie","kategorie":"Yachten"}'
    assert frage.parse_auswahl(roh, KATEGORIEN)[0] is None


def test_kategorie_ohne_angabe_wird_verworfen():
    assert frage.parse_auswahl('{"funktion":"kategorie"}', KATEGORIEN)[0] is None


def test_unbekannte_funktion_wird_verworfen():
    assert frage.parse_auswahl('{"funktion":"aktienkurs"}', KATEGORIEN)[0] is None


def test_kein_json_wird_verworfen():
    assert frage.parse_auswahl("Ich denke, du hast 200 Euro ausgegeben.", KATEGORIEN)[0] is None
    assert frage.parse_auswahl("", KATEGORIEN)[0] is None
    assert frage.parse_auswahl(None, KATEGORIEN)[0] is None


def test_unbekannter_zeitraum_faellt_auf_monat_zurueck():
    roh = '{"funktion":"top5","zeitraum":"letztes jahr"}'
    assert frage.parse_auswahl(roh, KATEGORIEN) == ("top5", None, "monat")


def test_vormonat_wird_uebernommen():
    roh = '{"funktion":"top5","zeitraum":"vormonat"}'
    assert frage.parse_auswahl(roh, KATEGORIEN)[2] == "vormonat"


def test_funktion_ohne_kategorie_ist_erlaubt():
    assert frage.parse_auswahl('{"funktion":"saldo"}', KATEGORIEN) == ("saldo", None, "monat")


def test_prompt_nennt_die_kategorien_und_verbietet_rechnen():
    p = frage.baue_prompt("wie viel fuer essen", KATEGORIEN)
    assert "Lebensmittel" in p
    assert "Rechne nichts" in p


def test_formatiere_kategorie_ohne_ausgaben():
    text = frage.formatiere_kategorie("Restaurant", 0.0, "2026-08-01", "2026-08-20")
    assert "Keine Ausgaben" in text


def test_formatiere_kategorie_mit_betrag():
    text = frage.formatiere_kategorie("Restaurant", 60.82, "2026-08-01", "2026-08-20")
    assert "60.82" in text
