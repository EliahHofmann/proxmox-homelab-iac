import datetime

import advisor
from advisor import (
    previous_month_range,
    month_before_range,
    parse_insight,
    build_report_json,
)


def test_previous_month_range():
    assert previous_month_range(datetime.date(2026, 7, 1)) == ("2026-06-01", "2026-06-30")


def test_previous_month_range_over_year_boundary():
    assert previous_month_range(datetime.date(2026, 1, 1)) == ("2025-12-01", "2025-12-31")


def test_month_before_range():
    assert month_before_range("2026-06-01") == ("2026-05-01", "2026-05-31")


def test_parse_insight_makes_expenses_positive():
    payload = [
        {"name": "Lebensmittel", "difference_float": -420.5},
        {"name": "Abos", "difference_float": -12.99},
    ]
    assert parse_insight(payload) == {"Lebensmittel": 420.5, "Abos": 12.99}


def test_parse_insight_skips_zero():
    payload = [{"name": "Leer", "difference_float": 0.0},
               {"name": "Abos", "difference_float": -5.0}]
    assert parse_insight(payload) == {"Abos": 5.0}


def test_build_report_totals():
    r = build_report_json({"Lebensmittel": 400.0, "Abos": 100.0},
                          {"Lebensmittel": 380.0, "Abos": 100.0}, "2026-06")
    assert r["monat"] == "2026-06"
    assert r["gesamtausgaben_euro"] == 500.0
    assert r["vormonat_gesamt_euro"] == 480.0
    assert r["delta_gesamt_euro"] == 20.0


def test_build_report_delta_prozent_and_trend():
    r = build_report_json({"Lebensmittel": 440.0}, {"Lebensmittel": 400.0}, "2026-06")
    kat = r["kategorien"][0]
    assert kat["delta_euro"] == 40.0
    assert kat["delta_prozent"] == 10.0
    assert kat["trend"] == "gestiegen"


def test_build_report_trend_stabil_unter_schwelle():
    r = build_report_json({"Abos": 102.0}, {"Abos": 100.0}, "2026-06")
    assert r["kategorien"][0]["trend"] == "stabil"


def test_build_report_neue_kategorie_ohne_prozent():
    r = build_report_json({"Elektronik": 250.0}, {}, "2026-06")
    kat = r["kategorien"][0]
    assert kat["vormonat_euro"] == 0.0
    assert kat["delta_prozent"] is None
    assert kat["trend"] == "neu"


def test_build_report_sortiert_und_top3():
    r = build_report_json(
        {"Abos": 50.0, "Lebensmittel": 400.0, "Restaurant": 120.0, "Drogerie": 20.0},
        {}, "2026-06")
    assert [k["name"] for k in r["kategorien"]] == [
        "Lebensmittel", "Restaurant", "Abos", "Drogerie"]
    assert r["top_3"] == ["Lebensmittel", "Restaurant", "Abos"]


def test_build_report_anteil_prozent():
    r = build_report_json({"A": 750.0, "B": 250.0}, {}, "2026-06")
    assert r["kategorien"][0]["anteil_prozent"] == 75.0
    assert r["kategorien"][1]["anteil_prozent"] == 25.0


def test_build_report_leerer_monat():
    r = build_report_json({}, {}, "2026-06")
    assert r["gesamtausgaben_euro"] == 0.0
    assert r["kategorien"] == []
    assert r["top_3"] == []
    assert r["delta_gesamt_prozent"] is None


def test_send_ntfy_nutzt_basic_auth_ohne_token(monkeypatch):
    # ntfy laeuft mit deny-all -> ohne Anmeldung 403.
    gesehen = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        gesehen["headers"] = headers

        class R:
            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(advisor.requests, "post", fake_post)
    advisor.send_ntfy("text", "http://ntfy/finanzen", "", "publisher", "geheim")
    # base64("publisher:geheim")
    assert gesehen["headers"]["Authorization"] == "Basic cHVibGlzaGVyOmdlaGVpbQ=="


def test_send_ntfy_token_schlaegt_basic_auth(monkeypatch):
    gesehen = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        gesehen["headers"] = headers

        class R:
            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(advisor.requests, "post", fake_post)
    advisor.send_ntfy("text", "http://ntfy/finanzen", "tk_123", "publisher", "geheim")
    assert gesehen["headers"]["Authorization"] == "Bearer tk_123"


def test_send_ntfy_ohne_zugangsdaten_ohne_header(monkeypatch):
    gesehen = {}

    def fake_post(url, data=None, headers=None, timeout=None):
        gesehen["headers"] = headers

        class R:
            def raise_for_status(self):
                pass
        return R()

    monkeypatch.setattr(advisor.requests, "post", fake_post)
    advisor.send_ntfy("text", "http://ntfy/finanzen")
    assert "Authorization" not in gesehen["headers"]
# ---- Nicht-Konsum-Kategorien (Darlehen/Investment verzerren jeden Vergleich) ----
def test_filter_konsum_entfernt_darlehen_und_investment():
    from advisor import filter_konsum
    assert filter_konsum({"Lebensmittel": 400.0, "Darlehen": 210.0,
                          "Investment": 1390.0}) == {"Lebensmittel": 400.0}


def test_filter_konsum_laesst_normale_kategorien_stehen():
    from advisor import filter_konsum
    daten = {"Lebensmittel": 400.0, "Gaming": 21.64, "Jugendfreizeit": 59.26}
    assert filter_konsum(daten) == daten


# ---- Einnahmen & Sparquote ----
def test_parse_income_nimmt_nur_die_einkommens_kategorie():
    from advisor import parse_income
    payload = [{"name": "Darlehen", "difference_float": 80},
               {"name": "Einkommen", "difference_float": 1275.05},
               {"name": "Erstattung", "difference_float": 350}]
    assert parse_income(payload) == 1275.05


def test_parse_income_ohne_einkommen_ist_null():
    from advisor import parse_income
    assert parse_income([{"name": "Erstattung", "difference_float": 350}]) == 0.0


def test_sparquote_rechnet_anteil_der_nicht_verkonsumiert_wurde():
    from advisor import sparquote
    assert sparquote(1000.0, 250.0) == 75.0


def test_sparquote_negativ_wenn_mehr_ausgegeben_als_eingenommen():
    from advisor import sparquote
    assert sparquote(1000.0, 1200.0) == -20.0


def test_sparquote_ohne_einnahmen_ist_none():
    from advisor import sparquote
    assert sparquote(0.0, 100.0) is None


def test_build_report_mit_einnahmen():
    r = build_report_json({"Lebensmittel": 250.0}, {}, "2026-07", einnahmen=1000.0)
    assert r["einnahmen_euro"] == 1000.0
    assert r["sparquote_prozent"] == 75.0


def test_build_report_ohne_einnahmen_bleibt_rueckwaertskompatibel():
    r = build_report_json({"Lebensmittel": 250.0}, {}, "2026-07")
    assert r["einnahmen_euro"] is None
    assert r["sparquote_prozent"] is None


def test_build_report_vormonats_sparquote():
    """Ohne Vergleichswert wuerde die KI 'gestiegen/gesunken' erfinden."""
    r = build_report_json({"Lebensmittel": 250.0}, {"Lebensmittel": 500.0}, "2026-07",
                          einnahmen=1000.0, einnahmen_vor=1000.0)
    assert r["sparquote_prozent"] == 75.0
    assert r["sparquote_vormonat_prozent"] == 50.0


def test_build_report_ohne_vormonats_einnahmen_ist_none():
    r = build_report_json({"Lebensmittel": 250.0}, {}, "2026-07", einnahmen=1000.0)
    assert r["sparquote_vormonat_prozent"] is None
