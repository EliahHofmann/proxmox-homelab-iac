"""Freie Fragen beantworten - ohne dem Modell eine einzige Zahl zu zeigen.

Das Modell bekommt die Frage und eine Liste moeglicher Abfragen. Es antwortet
nur mit der Auswahl (welche Abfrage, welche Kategorie, welcher Zeitraum).
Gerechnet wird ausschliesslich in Python. Damit kann das Modell keine Betraege
erfinden - es sieht keine.
"""
import json
import datetime

import requests

FUNKTIONEN = ("kategorie", "bericht", "saldo", "top5", "sparquote")
ZEITRAEUME = ("monat", "vormonat")
TIMEOUT = 300

SCHEMA = {
    "type": "object",
    "properties": {
        "funktion": {"type": "string", "enum": list(FUNKTIONEN)},
        "kategorie": {"type": "string"},
        "zeitraum": {"type": "string", "enum": list(ZEITRAEUME)},
    },
    "required": ["funktion"],
}


def baue_prompt(frage, kategorien):
    return (
        "Du ordnest eine Frage einer von fuenf Abfragen zu. Antworte NUR mit JSON.\n\n"
        "funktion:\n"
        "- kategorie: Ausgaben einer bestimmten Kategorie (dann kategorie setzen)\n"
        "- bericht: alle Ausgaben nach Kategorie\n"
        "- saldo: Kontostaende und Vermoegen\n"
        "- top5: groesste Einzelausgaben\n"
        "- sparquote: Einnahmen gegen Ausgaben\n\n"
        f"kategorie: eine aus dieser Liste: {', '.join(kategorien)}\n"
        "zeitraum: monat (laufender Monat) oder vormonat\n\n"
        "Rechne nichts und nenne keine Betraege. Waehle nur aus.\n\n"
        f"Frage: {frage}"
    )


def parse_auswahl(raw, kategorien):
    """Modellantwort -> (funktion, kategorie, zeitraum). Unbrauchbares -> (None, ...)."""
    try:
        d = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return None, None, "monat"
    if not isinstance(d, dict):
        return None, None, "monat"

    funktion = str(d.get("funktion", "")).strip().lower()
    if funktion not in FUNKTIONEN:
        return None, None, "monat"

    zeitraum = str(d.get("zeitraum", "monat")).strip().lower()
    if zeitraum not in ZEITRAEUME:
        zeitraum = "monat"

    kategorie = None
    roh = str(d.get("kategorie", "")).strip()
    if roh:
        for k in kategorien:                       # nur bekannte Kategorien gelten
            if k.lower() == roh.lower():
                kategorie = k
                break
    if funktion == "kategorie" and not kategorie:
        return None, None, zeitraum                # ohne Kategorie ist die Abfrage sinnlos
    return funktion, kategorie, zeitraum


def frag_modell(frage, kategorien, url, model):
    payload = {"model": model, "prompt": baue_prompt(frage, kategorien), "stream": False,
               "format": SCHEMA, "options": {"temperature": 0.1, "num_predict": 120}}
    r = requests.post(url, json=payload, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json().get("response", "")


def zeitraum_grenzen(zeitraum, heute=None):
    from advisor import previous_month_range
    from kommando import monat_bis_heute
    heute = heute or datetime.date.today()
    return previous_month_range(heute) if zeitraum == "vormonat" else monat_bis_heute(heute)


def formatiere_kategorie(name, betrag, start, ende):
    if betrag <= 0:
        return f"Keine Ausgaben fuer {name} zwischen {start} und {ende}."
    return f"{name}: {betrag:.2f} EUR\n\nZeitraum {start} bis {ende}"


def beantworte_frage(frage, base, pat, url, model, heute=None):
    from advisor import fetch_expenses, filter_konsum
    from kommando import beantworte, formatiere_bericht

    kategorien = sorted(filter_konsum(fetch_expenses(base, pat, *zeitraum_grenzen("vormonat", heute))).keys()
                        | filter_konsum(fetch_expenses(base, pat, *zeitraum_grenzen("monat", heute))).keys())
    if not kategorien:
        kategorien = ["Lebensmittel", "Restaurant", "Online-Shopping", "Sonstiges"]

    funktion, kategorie, zeitraum = parse_auswahl(
        frag_modell(frage, kategorien, url, model), kategorien)
    if funktion is None:
        return ("Die Frage habe ich nicht verstanden.\n\n"
                "Moeglich sind zum Beispiel:\n"
                "- wie viel habe ich diesen Monat fuer Lebensmittel ausgegeben\n"
                "- was waren letzten Monat meine groessten Ausgaben\n"
                "- wie ist mein Kontostand")

    start, ende = zeitraum_grenzen(zeitraum, heute)
    if funktion == "kategorie":
        betraege = filter_konsum(fetch_expenses(base, pat, start, ende))
        return formatiere_kategorie(kategorie, betraege.get(kategorie, 0.0), start, ende)
    if funktion == "bericht" and zeitraum == "vormonat":
        return formatiere_bericht(filter_konsum(fetch_expenses(base, pat, start, ende)), start, ende)
    return beantworte(funktion, base, pat, heute)
