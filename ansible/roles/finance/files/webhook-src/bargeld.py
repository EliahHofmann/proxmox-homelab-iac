"""Bargeld per Nachricht erfassen: Zugang aufs Portemonnaie und Barausgaben.

Seit der Umstellung ist eine Abhebung kein Konsum mehr, sondern eine Umbuchung
aufs Bargeld-Konto (siehe categorize.py). Konsum entsteht erst hier, wenn eine
einzelne Barausgabe erfasst wird - sonst waere jede Erfassung eine Doppelzaehlung.
"""
import re
import datetime

import requests

from firefly import ASSET_CASH

# Sammelkonto fuer Barausgaben. Ein Konto je Imbiss waere unuebersichtlich,
# der Zweck steht in der Beschreibung.
EXPENSE_BAR = "Barausgabe"
QUELLE_BAR = "Bargeld erhalten"
OBERGRENZE = 1000.0
TIMEOUT = 60

BETRAG_RE = re.compile(r"^\d{1,4}([.,]\d{1,2})?$")


def parse_betrag(wort):
    """'12,50' oder '12.5' -> 12.5. Alles andere -> None."""
    if not wort or not BETRAG_RE.match(str(wort)):
        return None
    betrag = round(float(str(wort).replace(",", ".")), 2)
    if betrag <= 0 or betrag > OBERGRENZE:
        return None
    return betrag


def parse_bargeld(text):
    """Zerlegt die Nachricht in (art, betrag, beschreibung).

    art ist 'zugang', 'ausgabe' oder None, wenn die Nachricht unbrauchbar ist.
    """
    worte = str(text or "").split()
    if not worte or worte[0].lower() != "bargeld":
        return None, None, ""
    rest = worte[1:]
    art = "zugang"
    if rest and rest[0].lower() in ("ausgabe", "ausgeben", "raus"):
        art = "ausgabe"
        rest = rest[1:]
    if not rest:
        return None, None, ""
    betrag = parse_betrag(rest[0])
    if betrag is None:
        return None, None, ""
    beschreibung = " ".join(rest[1:]).strip()
    return art, betrag, beschreibung[:80]


def hilfetext():
    return ("So wird Bargeld erfasst:\n\n"
            "- bargeld 50            50 EUR ins Portemonnaie\n"
            "- bargeld 50 von Oma    dito, mit Notiz\n"
            "- bargeld ausgabe 12,50 Doener Imbiss\n\n"
            f"Betrag mit Komma oder Punkt, hoechstens {OBERGRENZE:.0f} EUR.")


def _kategorie_fuer(beschreibung):
    """Nutzt dieselben Muster wie der taegliche Kategorisierer."""
    from categorize import match_category
    return match_category(beschreibung) or "Sonstiges"


def baue_buchung(art, betrag, beschreibung, heute=None):
    datum = (heute or datetime.date.today()).isoformat()
    if art == "ausgabe":
        return {"transactions": [{
            "type": "withdrawal", "date": datum, "amount": f"{betrag:.2f}",
            "description": beschreibung or "Barausgabe",
            "source_name": ASSET_CASH, "destination_name": EXPENSE_BAR,
            "category_name": _kategorie_fuer(beschreibung),
            "tags": ["bar", "manuell"],
        }]}
    return {"transactions": [{
        "type": "deposit", "date": datum, "amount": f"{betrag:.2f}",
        "description": beschreibung or "Bargeld erhalten",
        "source_name": QUELLE_BAR, "destination_name": ASSET_CASH,
        "tags": ["bar", "manuell"],
    }]}


def kontostand(base, token, konto=ASSET_CASH):
    r = requests.get(f"{base.rstrip('/')}/api/v1/accounts", params={"type": "asset"},
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    for e in r.json().get("data", []):
        a = e.get("attributes", {})
        if a.get("name") == konto:
            try:
                return round(float(a.get("current_balance", 0)), 2)
            except (TypeError, ValueError):
                return None
    return None


def buche(base, token, payload):
    r = requests.post(f"{base.rstrip('/')}/api/v1/transactions", json=payload,
                      headers={"Authorization": f"Bearer {token}",
                               "Content-Type": "application/json",
                               "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return r.json()


def verarbeite(text, base, token, heute=None):
    """Nachricht -> Antworttext. Bucht nur, wenn die Angaben eindeutig sind."""
    art, betrag, beschreibung = parse_bargeld(text)
    if art is None:
        return hilfetext()
    buche(base, token, baue_buchung(art, betrag, beschreibung, heute))
    stand = kontostand(base, token)
    richtung = "Ausgabe" if art == "ausgabe" else "Zugang"
    zeile = f"{richtung}: {betrag:.2f} EUR"
    if beschreibung:
        zeile += f" ({beschreibung})"
    if stand is not None:
        zeile += f"\n\nBargeld jetzt: {stand:.2f} EUR"
    return zeile
