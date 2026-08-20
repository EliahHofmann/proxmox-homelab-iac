import datetime

import alarme


def test_hohe_buchung_wird_gemeldet():
    treffer = alarme.hohe_einzelbuchungen([("1", "2026-08-20", "Zelt", 179.60)])
    assert len(treffer) == 1
    assert "179.60" in treffer[0][1]


def test_kleine_buchung_bleibt_still():
    assert alarme.hohe_einzelbuchungen([("1", "2026-08-20", "Kaffee", 3.20)]) == []


def test_hochrechnung_zur_monatsmitte():
    # 100 EUR nach 10 von 31 Tagen -> 310 EUR erwartet
    assert round(alarme.hochrechnung(100.0, datetime.date(2026, 8, 10))) == 310


def test_kategorie_ueber_vormonat_wird_gemeldet():
    heute = datetime.date(2026, 8, 10)
    treffer = alarme.kategorien_ausreisser({"Restaurant": 100.0}, {"Restaurant": 120.0}, heute)
    assert len(treffer) == 1
    assert "Restaurant" in treffer[0][1]


def test_kategorie_im_rahmen_bleibt_still():
    heute = datetime.date(2026, 8, 10)
    assert alarme.kategorien_ausreisser({"Restaurant": 30.0}, {"Restaurant": 120.0}, heute) == []


def test_neue_kategorie_ist_kein_ausreisser():
    heute = datetime.date(2026, 8, 10)
    assert alarme.kategorien_ausreisser({"Urlaub": 500.0}, {}, heute) == []


def test_abo_erhoehung_wird_erkannt():
    treffer = alarme.abo_erhoehungen({"Spotify": 12.99}, {"Spotify": 10.99})
    assert len(treffer) == 1
    assert "10.99 -> 12.99" in treffer[0][1]


def test_gleicher_abo_preis_bleibt_still():
    assert alarme.abo_erhoehungen({"Spotify": 10.99}, {"Spotify": 10.99}) == []


def test_neues_abo_ist_keine_erhoehung():
    assert alarme.abo_erhoehungen({"Neu": 5.0}, {}) == []


def test_knapper_kontostand():
    treffer = alarme.konto_knapp(42.0, heute=datetime.date(2026, 8, 20))
    assert len(treffer) == 1
    assert "42.00" in treffer[0][1]


def test_ausreichender_kontostand_bleibt_still():
    assert alarme.konto_knapp(500.0) == []
    assert alarme.konto_knapp(None) == []


def test_meldung_ueberspringt_bereits_gemeldetes():
    gruppen = [("Hohe Buchungen:", [("buchung:1", "alt"), ("buchung:2", "neu")])]
    text, neu = alarme.baue_meldung(gruppen, gemeldet={"buchung:1"})
    assert "neu" in text
    assert "alt" not in text
    assert neu == {"buchung:2"}


def test_meldung_faellt_aus_wenn_alles_bekannt():
    gruppen = [("Hohe Buchungen:", [("buchung:1", "alt")])]
    text, neu = alarme.baue_meldung(gruppen, gemeldet={"buchung:1"})
    assert text is None
    assert neu == set()


def test_meldung_ohne_treffer():
    assert alarme.baue_meldung([("Titel", [])], set()) == (None, set())


def test_zustand_wird_gespeichert_und_gelesen(tmp_path):
    pfad = str(tmp_path / "alarme.json")
    alarme.speichere_gemeldet({"buchung:7"}, pfad)
    assert alarme.lade_gemeldet(pfad) == {"buchung:7"}


def test_fehlende_zustandsdatei_ist_kein_fehler(tmp_path):
    assert alarme.lade_gemeldet(str(tmp_path / "gibtsnicht.json")) == set()
