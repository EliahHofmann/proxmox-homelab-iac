"""Manuelle Umbuchungen zwischen den eigenen Konten (C24, IBKR, Kraken).

Hintergrund: Nur die Sparkasse haengt an Enable Banking. Die C24-Anbindung
liefert dort (Stand 08/2026) beim Callback "server_error", der Konnektor ist
als beta markiert. Bewegungen wie "C24 Investment -> IBKR" sieht Firefly
deshalb nicht automatisch. Dieses Skript traegt sie in einem Befehl nach.

    docker exec finance-webhook python /app/umbuchung.py ibkr 400
    docker exec finance-webhook python /app/umbuchung.py sparen 500 --datum 01.08.2026
    docker exec finance-webhook python /app/umbuchung.py --liste
"""
import argparse
import datetime
import os
import re
import sys

# Kurzwort -> (Quellkonto, Zielkonto). Namen muessen exakt den Firefly-Konten
# entsprechen, sonst legt die API stillschweigend ein neues Konto an.
WEGE = {
    "sparen":  ("Sparkasse Giro", "Investment Sparkonto (C24)"),
    "urlaub":  ("Sparkasse Giro", "Urlaub Sparkonto (C24)"),
    "ibkr":    ("Investment Sparkonto (C24)", "IBKR Depot"),
    "kraken":  ("Investment Sparkonto (C24)", "Kraken"),
    "zurueck": ("Investment Sparkonto (C24)", "Sparkasse Giro"),
}


def parse_betrag(text):
    """'1.234,56 EUR' -> 1234.56. Wirft ValueError bei <= 0 oder Unsinn."""
    s = re.sub(r"[^\d,.\-]", "", str(text or ""))
    if not s:
        raise ValueError("Kein Betrag erkannt")
    # Deutsches Format: Punkt ist Tausendertrenner, Komma das Dezimalzeichen
    if "," in s:
        s = s.replace(".", "").replace(",", ".")
    try:
        wert = float(s)
    except ValueError:
        raise ValueError(f"Betrag nicht lesbar: {text!r}")
    if wert <= 0:
        raise ValueError(f"Betrag muss groesser als 0 sein: {text!r}")
    return round(wert, 2)


def parse_datum(text, heute=None):
    """Leer -> heute. Akzeptiert 05.08.2026 und 2026-08-05."""
    if not text:
        return (heute or datetime.date.today()).isoformat()
    text = str(text).strip()
    for fmt in ("%Y-%m-%d", "%d.%m.%Y", "%d.%m.%y"):
        try:
            return datetime.datetime.strptime(text, fmt).date().isoformat()
        except ValueError:
            continue
    raise ValueError(f"Datum nicht lesbar: {text!r} (erwartet 05.08.2026 oder 2026-08-05)")


def weg_aufloesen(weg):
    key = str(weg or "").strip().lower()
    if key not in WEGE:
        raise ValueError(f"Unbekannter Weg {weg!r}. Gueltig: {', '.join(sorted(WEGE))}")
    return WEGE[key]


def baue_transfer(weg, betrag, datum, notiz=None):
    quelle, ziel = weg_aufloesen(weg)
    return {
        # Firefly lehnt eine identische Buchung ab statt sie doppelt anzulegen
        "error_if_duplicate_hash": True,
        # Transfers brauchen keine Kategorie - Regeln wuerden nur stoeren
        "apply_rules": False,
        "transactions": [{
            "type": "transfer",
            "date": datum,
            "amount": f"{float(betrag):.2f}",
            "description": f"{quelle} -> {ziel}",
            "source_name": quelle,
            "destination_name": ziel,
            # macht manuelle Buchungen von importierten unterscheidbar
            "tags": ["manuell"],
            "notes": notiz or "Manuell erfasst (Konto haengt nicht am Bank-Import)",
        }],
    }


def main(argv=None):
    p = argparse.ArgumentParser(
        description="Umbuchung zwischen eigenen Konten in Firefly eintragen.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="Wege:\n" + "\n".join(f"  {k:<9} {v[0]} -> {v[1]}"
                                     for k, v in sorted(WEGE.items())))
    p.add_argument("weg", nargs="?", help="sparen | urlaub | ibkr | kraken | zurueck")
    p.add_argument("betrag", nargs="?", help='z.B. 400 oder "1.234,56"')
    p.add_argument("--datum", default="", help="05.08.2026 (Standard: heute)")
    p.add_argument("--notiz", default="", help="freier Text")
    p.add_argument("--liste", action="store_true", help="nur die Wege anzeigen")
    a = p.parse_args(argv)

    if a.liste or not a.weg or not a.betrag:
        print("Wege:")
        for k, (q, z) in sorted(WEGE.items()):
            print(f"  {k:<9} {q}  ->  {z}")
        print('\nBeispiel: umbuchung.py ibkr 400 --datum 01.08.2026')
        return 0 if a.liste else 1

    try:
        betrag = parse_betrag(a.betrag)
        datum = parse_datum(a.datum)
        payload = baue_transfer(a.weg, betrag, datum, a.notiz or None)
    except ValueError as e:
        print(f"Fehler: {e}", file=sys.stderr)
        return 2

    from firefly import FireflyClient
    fc = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])
    t = payload["transactions"][0]
    try:
        fc.create_withdrawal(payload)     # POST /transactions, Typ steckt im Payload
    except Exception as e:
        # Der haeufigste Fall: exakt diese Buchung gibt es schon.
        print(f"Nicht gebucht: {e}", file=sys.stderr)
        return 3
    print(f"Gebucht: {datum}  {betrag:.2f} EUR   {t['source_name']} -> {t['destination_name']}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
