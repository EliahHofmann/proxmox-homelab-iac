"""Beantwortet Kommandos aus dem ntfy-Topic finance-cmd.

Aufgerufen von ntfy_listener.py, der das Topic abonniert - die Nachricht kommt
als erstes Argument (oder in der Umgebungsvariable $message).

Alle Zahlen werden hier in Python berechnet - genau wie im Monatsbericht. Die KI
kommt hier gar nicht vor, damit nichts erfunden werden kann.
"""
import os
import sys
import datetime
import requests

from advisor import fetch_expenses, filter_konsum, fetch_income, sparquote, send_ntfy
import slog

KOMMANDOS = ("bericht", "saldo", "top5", "sparquote", "hilfe")
TIMEOUT = 60


def parse_kommando(text):
    """Erstes Wort, klein geschrieben. Alles Unbekannte wird zur Hilfe."""
    if not text:
        return "hilfe"
    erstes = str(text).strip().split()
    if not erstes:
        return "hilfe"
    wort = erstes[0].lower()
    return wort if wort in KOMMANDOS else "hilfe"


def monat_bis_heute(today=None):
    """(start, end) vom Monatsersten bis heute - der Zeitraum, der noch laeuft."""
    today = today or datetime.date.today()
    return today.replace(day=1).isoformat(), today.isoformat()


# ---------- Firefly-Abfragen ----------
def parse_accounts(payload):
    """Aktive Bestandskonten als (Name, Saldo)."""
    konten = []
    for eintrag in payload.get("data", []):
        a = eintrag.get("attributes", {})
        if a.get("type") != "asset" or not a.get("active", True):
            continue
        try:
            konten.append((a.get("name", "?"), round(float(a.get("current_balance", 0)), 2)))
        except (TypeError, ValueError):
            continue
    return konten


def parse_transactions(payload):
    """Ausgaben als (Beschreibung, Betrag). Transfers zaehlen nicht als Ausgabe."""
    posten = []
    for eintrag in payload.get("data", []):
        for t in eintrag.get("attributes", {}).get("transactions", []):
            if t.get("type") != "withdrawal":
                continue
            try:
                posten.append((t.get("description", "?"), round(float(t.get("amount", 0)), 2)))
            except (TypeError, ValueError):
                continue
    return posten


def fetch_accounts(base, token):
    r = requests.get(f"{base.rstrip('/')}/api/v1/accounts", params={"type": "asset"},
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return parse_accounts(r.json())


def fetch_transactions(base, token, start, end):
    r = requests.get(f"{base.rstrip('/')}/api/v1/transactions",
                     params={"start": start, "end": end, "type": "withdrawal", "limit": 200},
                     headers={"Authorization": f"Bearer {token}",
                              "Accept": "application/json"}, timeout=TIMEOUT)
    r.raise_for_status()
    return parse_transactions(r.json())


# ---------- Formatierung ----------
def formatiere_bericht(kategorien, start, end):
    if not kategorien:
        return f"Keine Ausgaben zwischen {start} und {end}."
    gesamt = sum(kategorien.values())
    zeilen = [f"Ausgaben {start} bis {end}: {gesamt:.2f} EUR", ""]
    for name, betrag in sorted(kategorien.items(), key=lambda x: -x[1])[:8]:
        anteil = betrag / gesamt * 100 if gesamt else 0
        zeilen.append(f"- {name}: {betrag:.2f} EUR ({anteil:.0f} %)")
    return "\n".join(zeilen)


def formatiere_saldo(konten):
    if not konten:
        return "Keine Bestandskonten gefunden."
    zeilen = [f"Vermoegen: {sum(b for _, b in konten):.2f} EUR", ""]
    for name, betrag in sorted(konten, key=lambda x: -x[1]):
        zeilen.append(f"- {name}: {betrag:.2f} EUR")
    return "\n".join(zeilen)


def formatiere_top(posten, anzahl=5):
    if not posten:
        return "Keine Ausgaben in diesem Zeitraum."
    zeilen = [f"Groesste {anzahl} Ausgaben diesen Monat:", ""]
    for beschreibung, betrag in sorted(posten, key=lambda x: -x[1])[:anzahl]:
        zeilen.append(f"- {betrag:.2f} EUR  {beschreibung[:40]}")
    return "\n".join(zeilen)


def formatiere_sparquote(einnahmen, konsum):
    quote = sparquote(einnahmen, konsum)
    if quote is None:
        return "Noch keine Einnahmen in diesem Monat erfasst."
    return (f"Sparquote diesen Monat: {quote:.1f} %\n\n"
            f"Einnahmen: {einnahmen:.2f} EUR\nKonsum: {konsum:.2f} EUR\n"
            f"Uebrig: {einnahmen - konsum:.2f} EUR")


def formatiere_hilfe():
    return ("Moegliche Kommandos:\n\n"
            "- bericht: Ausgaben vom Monatsanfang bis heute\n"
            "- saldo: alle Kontostaende\n"
            "- top5: groesste Einzelausgaben des Monats\n"
            "- sparquote: Einnahmen gegen Konsum\n"
            "- hilfe: diese Uebersicht")


# ---------- Ablauf ----------
def beantworte(kommando, base, pat, today=None):
    start, end = monat_bis_heute(today)
    if kommando == "bericht":
        return formatiere_bericht(filter_konsum(fetch_expenses(base, pat, start, end)), start, end)
    if kommando == "saldo":
        return formatiere_saldo(fetch_accounts(base, pat))
    if kommando == "top5":
        return formatiere_top(fetch_transactions(base, pat, start, end))
    if kommando == "sparquote":
        konsum = sum(filter_konsum(fetch_expenses(base, pat, start, end)).values())
        return formatiere_sparquote(fetch_income(base, pat, start, end), konsum)
    return formatiere_hilfe()


def aktionen(cmd_url, user, password):
    """Action-Buttons fuer die uebrigen Kommandos.

    Die Zugangsdaten sind die des Lese-Benutzers - wer die Nachricht sieht, darf
    das Topic ohnehin lesen. Es wird also nichts preisgegeben, was der Empfaenger
    nicht schon haette.
    """
    if not (cmd_url and user and password):
        return None
    import base64
    auth = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
    knoepfe = []
    for k in ("bericht", "saldo", "top5"):
        knoepfe.append(f"http, {k}, {cmd_url}, method=POST, body={k}, "
                       f"headers.Authorization=Basic {auth}, clear=true")
    return "; ".join(knoepfe)


def main():
    nachricht = os.environ.get("message") or (sys.argv[1] if len(sys.argv) > 1 else "")
    kommando = parse_kommando(nachricht)
    base, pat = os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"]
    try:
        text = beantworte(kommando, base, pat)
    except Exception as e:
        slog.log_event("kommando_failed", kommando=kommando, error_type=type(e).__name__)
        text = f"Das Kommando '{kommando}' konnte nicht ausgefuehrt werden ({type(e).__name__})."
    knoepfe = aktionen(os.environ.get("NTFY_CMD_URL", ""),
                      os.environ.get("NTFY_READER_USER", ""),
                      os.environ.get("NTFY_READER_PASSWORD", ""))
    send_ntfy(text, os.environ["NTFY_URL"], os.environ.get("NTFY_TOKEN", ""),
              os.environ.get("NTFY_USER", ""), os.environ.get("NTFY_PASSWORD", ""),
              actions=knoepfe or "")
    slog.log_event("kommando_beantwortet", kommando=kommando)
    print(f"{kommando} beantwortet")


if __name__ == "__main__":
    main()
