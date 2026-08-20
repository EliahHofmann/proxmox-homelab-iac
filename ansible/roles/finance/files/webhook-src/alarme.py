"""Meldet auffaellige Buchungen, bevor sie im Monatsbericht auftauchen.

Laeuft taeglich nach der Kategorisierung. Meldet nur, wenn wirklich etwas
auffaellt - ein Push, der jeden Tag kommt, wird nach einer Woche ignoriert.
Bereits Gemeldetes merkt sich der Job, damit dieselbe Buchung nicht taeglich
erneut anklopft.

Alle Schwellen und Vergleiche werden hier gerechnet; ein Modell ist nicht
beteiligt.
"""
import os
import json
import calendar
import datetime

GRENZE_EINZELBUCHUNG = 150.0     # EUR
KATEGORIE_TOLERANZ = 1.5         # 50 % ueber dem Vormonat
GIRO_MINIMUM = 100.0             # EUR
ABO_TOLERANZ = 1.05              # 5 % teurer zaehlt als Erhoehung
STATE_DATEI = os.environ.get("ALARM_STATE", "/opt/finance-stack/metrics-state/alarme.json")


# ---------- Zustand ----------
def lade_gemeldet(pfad=None):
    try:
        with open(pfad or STATE_DATEI, encoding="utf-8") as f:
            return set(json.load(f).get("gemeldet", []))
    except (OSError, ValueError):
        return set()


def speichere_gemeldet(schluessel, pfad=None):
    ziel = pfad or STATE_DATEI
    try:
        os.makedirs(os.path.dirname(ziel), exist_ok=True)
        with open(ziel, "w", encoding="utf-8") as f:
            json.dump({"gemeldet": sorted(schluessel)}, f)
    except OSError:
        pass


# ---------- Pruefungen ----------
def hohe_einzelbuchungen(buchungen, grenze=GRENZE_EINZELBUCHUNG):
    """buchungen: [(id, datum, beschreibung, betrag)] -> [(schluessel, text)]"""
    treffer = []
    for bid, datum, beschreibung, betrag in buchungen:
        if betrag >= grenze:
            treffer.append((f"buchung:{bid}",
                            f"Hohe Buchung: {betrag:.2f} EUR am {datum[:10]} ({beschreibung})"))
    return treffer


def hochrechnung(betrag, heute):
    """Rechnet den bisherigen Monatsverbrauch auf den ganzen Monat hoch."""
    tage_im_monat = calendar.monthrange(heute.year, heute.month)[1]
    if heute.day < 1:
        return betrag
    return betrag / heute.day * tage_im_monat


def kategorien_ausreisser(aktuell, vormonat, heute, toleranz=KATEGORIE_TOLERANZ):
    """Kategorien, die hochgerechnet deutlich ueber dem Vormonat landen."""
    treffer = []
    monat = heute.strftime("%Y-%m")
    for name, betrag in sorted(aktuell.items(), key=lambda x: -x[1]):
        vor = vormonat.get(name, 0.0)
        if vor <= 0:
            continue                      # neue Kategorien sind kein Ausreisser
        erwartet = hochrechnung(betrag, heute)
        if erwartet > vor * toleranz:
            treffer.append((f"kategorie:{monat}:{name}",
                            f"{name}: {betrag:.2f} EUR bisher, hochgerechnet "
                            f"{erwartet:.0f} EUR gegen {vor:.0f} EUR im Vormonat"))
    return treffer


def abo_erhoehungen(aktuell, vormonat, toleranz=ABO_TOLERANZ):
    """Gleicher Empfaenger, hoeherer Betrag: stille Preiserhoehung.

    aktuell/vormonat: {empfaenger: betrag}
    """
    treffer = []
    for empfaenger, betrag in sorted(aktuell.items()):
        vor = vormonat.get(empfaenger)
        if not vor or betrag <= vor * toleranz:
            continue
        treffer.append((f"abo:{empfaenger}:{betrag:.2f}",
                        f"{empfaenger}: {vor:.2f} -> {betrag:.2f} EUR"))
    return treffer


def konto_knapp(saldo, minimum=GIRO_MINIMUM, heute=None):
    if saldo is None or saldo >= minimum:
        return []
    monat = (heute or datetime.date.today()).strftime("%Y-%m-%d")
    return [(f"knapp:{monat}", f"Girokonto: nur noch {saldo:.2f} EUR")]


# ---------- Zusammenbau ----------
def baue_meldung(gruppen, gemeldet):
    """gruppen: [(ueberschrift, [(schluessel, text)])] -> (text, neue_schluessel).

    Liefert (None, set()), wenn alles schon gemeldet wurde oder nichts anliegt.
    """
    zeilen = []
    neu = set()
    for ueberschrift, treffer in gruppen:
        frisch = [(s, t) for s, t in treffer if s not in gemeldet]
        if not frisch:
            continue
        zeilen.append(ueberschrift)
        for schluessel, text in frisch:
            zeilen.append(f"- {text}")
            neu.add(schluessel)
        zeilen.append("")
    if not neu:
        return None, set()
    return "\n".join(zeilen).strip(), neu


# ---------- Ablauf ----------
def _empfaenger_summen(posten):
    """[(datum, beschreibung, betrag, kategorie)] -> {beschreibung: groesster Betrag}.

    Fuer Abos genuegt der hoechste Betrag je Empfaenger im Monat.
    """
    summen = {}
    for _datum, beschreibung, betrag, _kat in posten:
        if beschreibung and betrag > summen.get(beschreibung, 0.0):
            summen[beschreibung] = betrag
    return summen


def run(heute=None):
    import time
    from advisor import fetch_expenses, filter_konsum, send_ntfy, previous_month_range
    from kommando import fetch_transactions, fetch_accounts, monat_bis_heute
    from metrics import JobMetrics
    import slog

    heute = heute or datetime.date.today()
    t0 = time.perf_counter()
    m = JobMetrics("alarme")
    try:
        base, pat = os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"]
        start, ende = monat_bis_heute(heute)
        vor_start, vor_ende = previous_month_range(heute)

        posten = fetch_transactions(base, pat, start, ende)
        posten_vor = fetch_transactions(base, pat, vor_start, vor_ende)
        konten = fetch_accounts(base, pat)
        giro = next((b for n, b in konten if n == "Sparkasse Giro"), None)

        gruppen = [
            ("Auffaellige Buchungen:",
             hohe_einzelbuchungen([(f"{d}-{b}-{be:.2f}", d, b, be) for d, b, be, _k in posten])),
            ("Kategorien ueber Vormonat:",
             kategorien_ausreisser(filter_konsum(fetch_expenses(base, pat, start, ende)),
                                   filter_konsum(fetch_expenses(base, pat, vor_start, vor_ende)),
                                   heute)),
            ("Teurer geworden:",
             abo_erhoehungen(_empfaenger_summen(posten), _empfaenger_summen(posten_vor))),
            ("Kontostand:", konto_knapp(giro, heute=heute)),
        ]

        gemeldet = lade_gemeldet()
        text, neu = baue_meldung(gruppen, gemeldet)
        if text:
            send_ntfy(text, os.environ["NTFY_URL"], os.environ.get("NTFY_TOKEN", ""),
                      os.environ.get("NTFY_USER", ""), os.environ.get("NTFY_PASSWORD", ""))
            speichere_gemeldet(gemeldet | neu)
        m.record_success(time.perf_counter() - t0)
        m.save()
        slog.log_event("alarme_run_success", meldungen=len(neu))
        print(f"Alarme: {len(neu)} neue Meldungen.")
    except Exception as e:
        m.record_failure(time.perf_counter() - t0)
        m.save()
        slog.log_event("alarme_run_failed", error_type=type(e).__name__)
        raise


if __name__ == "__main__":
    run()
