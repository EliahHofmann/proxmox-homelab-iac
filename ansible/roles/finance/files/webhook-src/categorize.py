"""Kategorisiert Bank-Buchungen anhand des Empfaengers (destination_name).

Laeuft per Cron NACH dem Bank-Import und VOR dem Matching-Job. Fasst nur
Buchungen OHNE Kategorie an -> bestehende Firefly-Regeln (Schwester, Abos,
Investieren) und Beleg-Kategorien werden nie ueberschrieben.

Muster erweitern: einfach den passenden Laden (klein geschrieben) in die Liste
der Kategorie eintragen. Teilstring-Match, Gross-/Kleinschreibung egal.
"""
import os
from firefly import FireflyClient, ASSET_BANK

# Kategorie -> Empfaenger-Muster (case-insensitive Teilstring im destination_name)
RULES = {
    "Lebensmittel":    ["netto", "edeka", "kaufland", "penny", "aldi", "ege market",
                        "blankenagel", "lidl", "rewe"],
    "Restaurant":      ["cafe neu", "mcdonald", "schloss burger", "seppels", "kikko",
                        "burger king", "subway"],
    "Freizeit":        ["bowling", "erlebnisgastronomie"],
    "Drogerie":        ["rossmann"],
    "Kleidung":        ["h+m", "jeans fritz", "c&a", "primark"],
    "Tanken":          ["aral", "shell", "esso"],
    "Fixkosten":       ["e-plus", "telekom", "vodafone"],
    "Bargeld":         ["ga nr"],
    "Online-Shopping": ["amazon"],
}


def match_category(dest):
    """Empfaenger -> Kategorie, oder None wenn kein Muster passt."""
    if not dest:
        return None
    d = dest.lower()
    for cat, patterns in RULES.items():
        if any(p in d for p in patterns):
            return cat
    return None


def run():
    fc = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])
    txs = fc._search_transactions(f'source_account_is:"{ASSET_BANK}" type:withdrawal')
    changed = 0
    for t in txs:
        if t.get("category_name"):      # schon kategorisiert -> nicht anfassen
            continue
        cat = match_category(t.get("destination_name"))
        if cat:
            fc.update_transaction(t["id"], t["journal_id"], {"category_name": cat})
            changed += 1
            print(f"Kategorisiert: {t.get('destination_name')} -> {cat} ({t['amount']}EUR)")
    print(f"Fertig: {changed} Buchungen kategorisiert.")


if __name__ == "__main__":
    run()
