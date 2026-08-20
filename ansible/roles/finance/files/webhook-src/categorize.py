"""Kategorisiert Bank-Buchungen anhand des Empfaengers (destination_name).

Laeuft per Cron NACH dem Bank-Import und VOR dem Matching-Job. Fasst nur
Buchungen OHNE Kategorie an -> bestehende Firefly-Regeln (Schwester, Abos,
Investieren) und Beleg-Kategorien werden nie ueberschrieben.

Muster erweitern: einfach den passenden Laden (klein geschrieben) in die Liste
der Kategorie eintragen. Teilstring-Match, Gross-/Kleinschreibung egal.
"""
import os
import re
import time
from firefly import FireflyClient, ASSET_BANK, ASSET_CASH
from metrics import JobMetrics
import slog

# Kategorie -> Empfaenger-Muster (case-insensitive Teilstring im destination_name)
#
# REIHENFOLGE IST BEDEUTSAM: die erste passende Kategorie gewinnt. Spezifische
# Haendler muessen deshalb VOR "Online-Shopping" stehen - dort faengt "paypal"
# sonst alles ab, was ueber PayPal bezahlt wurde (Games, Abos, Brettspiele).
RULES = {
    # Haendler der Jugendfreizeit 2026 (An-/Rueckreise + Kroatien).
    # ACHTUNG: Enable Banking liefert bei gebuchten Kartenzahlungen nur den
    # Acquirer ("Landesbank Hessen-Thuringen"), nicht den Haendler - der steht
    # nur im CSV-Export der Sparkasse. Diese Muster greifen deshalb nur, wenn
    # der Haendlername vorhanden ist. "konzum" fehlt bewusst: darunter laeuft
    # auch die vorgestreckte 170-EUR-Buchung, die keine Kategorie haben soll.
    "Jugendfreizeit":  ["ina bacva", "nyx", "pto seka", "tobacco rovinj",
                        "mlinar", "lidl hrvatska", "irschenberg"],
    "Abos & Software": ["openai", "chatgpt", "anthropic", "claude", "proton",
                        "netcup", "ionos", "strato", "namecheap", "cloudflare",
                        "digiphile"],
    "Gaming":          ["tebex", "steam", "valve", "nintendo", "playstation",
                        "sony interactive", "xbox", "epic games", "gog.com"],
    "Lebensmittel":    ["netto", "edeka", "kaufland", "penny", "aldi", "ege market",
                        "blankenagel", "lidl", "rewe", "mein-asiamarkt"],
    # Mensa/Uni-Cafe bewusst vor "Bildung" - dort wird gegessen, nicht studiert.
    "Restaurant":      ["cafe neu", "akademisches foerderungswerk", "mcdonald",
                        "schloss burger", "seppels", "kikko", "burger king",
                        "burgerking", "subway"],
    "Bildung":         ["westfaelische hochschule", "westfälische hochschule"],
    "Freizeit":        ["bowling", "erlebnisgastronomie", "bookshop"],
    "Drogerie":        ["rossmann"],
    "Kleidung":        ["h+m", "jeans fritz", "c&a", "primark"],
    "Tanken":          ["aral", "shell", "esso"],
    "Fixkosten":       ["e-plus", "telekom", "vodafone"],
    "Elektronik":      ["mediamarkt", "media markt", "saturn", "conrad"],
    "Online-Shopping": ["amazon", "paypal", "sammelkartenmarkt"],  # Auffangnetz - zuletzt
}

# Buchungen, bei denen nur der Acquirer uebrig bleibt, lassen sich ueber den
# Haendler nicht zuordnen - wohl aber ueber den Zeitraum, in dem sie anfielen.
# Die erste passende Regel gewinnt; ausserhalb des Fensters greift keine.
ZEITRAUM_RULES = [
    {
        "kategorie": "Jugendfreizeit",
        "muster": ["landesbank hessen-thuringen", "landesbank hessen-thüringen"],
        "von": "2026-07-18",
        "bis": "2026-07-31",
    },
]


ZAHLUNGSDATUM_RE = re.compile(r"(\d{4}-\d{2}-\d{2})T\d{2}:\d{2}")


def zahlungsdatum(beschreibung, buchungsdatum):
    """Wann wurde tatsaechlich gezahlt?

    Kartenzahlungen erscheinen Tage spaeter auf dem Konto; das Buchungsdatum
    taugt deshalb nicht zur Abgrenzung eines Aufenthalts. Die Bank stellt den
    echten Zeitpunkt an den Anfang der Beschreibung.
    """
    treffer = ZAHLUNGSDATUM_RE.search(str(beschreibung or ""))
    return treffer.group(1) if treffer else str(buchungsdatum or "")[:10]


def ist_abhebung(dest):
    """Geldautomat: der Empfaenger traegt die Automatenkennung."""
    return bool(dest) and "ga nr" in dest.lower()


def match_category(dest, datum=None, beschreibung=None):
    """Empfaenger (und notfalls der Zeitraum) -> Kategorie, sonst None."""
    if not dest:
        return None
    d = dest.lower()
    for cat, patterns in RULES.items():
        if any(p in d for p in patterns):
            return cat
    return match_zeitraum(d, zahlungsdatum(beschreibung, datum))


def match_zeitraum(dest_lower, datum):
    """Greift nur, wenn der Haendlername fehlt und das Datum im Fenster liegt."""
    if not datum:
        return None
    tag = str(datum)[:10]
    for regel in ZEITRAUM_RULES:
        if not any(p in dest_lower for p in regel["muster"]):
            continue
        if regel["von"] <= tag <= regel["bis"]:
            return regel["kategorie"]
    return None


def run():
    t0 = time.perf_counter()
    m = JobMetrics("categorize")
    try:
        fc = FireflyClient(os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"])
        txs = fc._search_transactions(f'source_account_is:"{ASSET_BANK}" type:withdrawal')
        changed = 0
        uncategorized = 0
        for t in txs:
            if t.get("category_name"):      # schon kategorisiert -> nicht anfassen
                continue
            if ist_abhebung(t.get("destination_name")):
                # Abhebungen sind kein Konsum, sondern eine Umbuchung ins
                # Portemonnaie. Ausgegeben wird das Geld erst spaeter, erfasst
                # ueber das Bargeld-Kommando.
                try:
                    fc.update_transaction(t["id"], t["journal_id"],
                                          {"type": "transfer",
                                           "destination_name": ASSET_CASH})
                    changed += 1
                except Exception as e:
                    slog.log_event("abhebung_umbuchen_fehlgeschlagen",
                                   error_type=type(e).__name__)
                continue
            cat = match_category(t.get("destination_name"), t.get("date"),
                                 t.get("description"))
            if cat:
                fc.update_transaction(t["id"], t["journal_id"], {"category_name": cat})
                changed += 1
                print(f"Kategorisiert: {t.get('destination_name')} -> {cat} ({t['amount']}EUR)")
            else:
                uncategorized += 1
        m.set_gauge("finance_uncategorized_transactions_count", uncategorized)
        m.record_success(time.perf_counter() - t0)
        m.save()
        slog.log_event("categorize_run_success", changed=changed, uncategorized=uncategorized)
        print(f"Fertig: {changed} Buchungen kategorisiert.")
    except Exception as e:
        m.record_failure(time.perf_counter() - t0)
        m.save()
        slog.log_event("categorize_run_failed", error_type=type(e).__name__)
        raise


if __name__ == "__main__":
    run()
