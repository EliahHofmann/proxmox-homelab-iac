"""KI-Finanzberater (Strom 3): Kategorie-Summen -> Ollama -> ntfy-Push.

Laeuft monatlich per Cron. Alle Zahlen (Deltas, Prozente, Anteile) werden hier
in Python berechnet; die KI darf ausschliesslich interpretieren, nicht rechnen.
Das ist der Halluzinationsschutz fuer das 8B-Modell.
"""
import os
import base64
import json
import time
import datetime
import requests

from metrics import JobMetrics
import slog

# Ab welcher Abweichung eine Kategorie als gestiegen/gesunken gilt
TREND_SCHWELLE_PROZENT = 5.0

# Kategorien, die zwar als Ausgabe gebucht sind, aber kein Konsum sind:
# "Darlehen" ist geliehenes Geld (kommt zurueck), "Investment" ist Sparen.
# Ohne diesen Filter verzerrt eine einzelne Sparrate den ganzen Monatsvergleich.
NICHT_KONSUM = {"Darlehen", "Investment"}

# Als Einkommen zaehlt nur diese Kategorie (Hilfskraft-Stelle + monatlicher
# Zuschuss). Alles andere, was auf dem Konto eingeht, ist Rueckfluss.
EINKOMMEN_KATEGORIE = "Einkommen"

ADVISOR_SYSTEM_PROMPT = """Du bist ein nuechterner Finanzberater fuer einen Privathaushalt.

Du bekommst einen fertig berechneten Monatsbericht als JSON. ALLE Zahlen darin
sind bereits korrekt berechnet.

REGELN:
1. Rechne NIEMALS selbst. Uebernimm Zahlen ausschliesslich woertlich aus dem JSON.
2. Erfinde keine Kategorien, Betraege oder Zeitraeume, die nicht im JSON stehen.
3. Erfinde KEINE konkreten Produkte, Geraete, Haendler, Anlaesse oder Ereignisse.
   Du weisst nur, welche Kategorie wie viel gekostet hat - warum, weisst du nicht.
   Falsch: "der Kauf des neuen Geraets". Richtig: "die Ausgaben in Elektronik".
4. Wenn eine Angabe fehlt, erwaehne sie nicht. Sage nicht, dass sie fehlt.
5. Keine Anlageberatung, keine Versicherungs- oder Kreditempfehlungen.
6. Antworte auf Deutsch, sachlich, ohne Floskeln.
   Sprich den Leser NIE an - kein "Sie", kein "Du", kein "Ihr/Dein".
   Formuliere unpersoenlich. Falsch: "Sie sollten Ihre Abos pruefen".
   Richtig: "Die Abo-Kosten sind gestiegen, eine Pruefung lohnt sich".
7. "sparquote_prozent" ist der Anteil der Einnahmen, der uebrig blieb. Ist der
   Wert negativ, wurde mehr ausgegeben als eingenommen - benenne das deutlich.
   Sparen und Darlehen sind in den Ausgaben NICHT enthalten, behaupte das nicht.
   Sage nur dann, die Sparquote sei gestiegen oder gesunken, wenn
   "sparquote_vormonat_prozent" gefuellt ist und der Vergleich das hergibt.

Antworte AUSSCHLIESSLICH mit gueltigem JSON in exakt dieser Form:
{
  "zusammenfassung": "Ein bis zwei Saetze zum Gesamtbild.",
  "tipps": ["Konkreter Tipp 1", "Konkreter Tipp 2", "Konkreter Tipp 3"]
}

Tipps NUR zu Kategorien, deren "trend" auf "gestiegen" oder "neu" steht, oder die
in "top_3" vorkommen. Gib NIEMALS einen Tipp zu einer Kategorie mit dem Trend
"gesunken" oder "stabil" - dort ist nichts zu tun. Gibt es keine solche Kategorie,
liefere eine leere Liste. Maximal 3 Tipps, je maximal 20 Woerter."""


# ---------- reine Logik (unit-getestet) ----------
def previous_month_range(today):
    """(start, end) des letzten vollen Monats als ISO-Strings."""
    end = today.replace(day=1) - datetime.timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


def month_before_range(start_iso):
    """(start, end) des Monats vor dem Monat, der bei start_iso beginnt."""
    end = datetime.date.fromisoformat(start_iso) - datetime.timedelta(days=1)
    return end.replace(day=1).isoformat(), end.isoformat()


def parse_insight(payload):
    """Firefly-Insight-Liste -> {Kategorie: positiver Betrag}. Ausgaben sind dort negativ."""
    out = {}
    for row in payload:
        betrag = abs(float(row.get("difference_float") or 0.0))
        if betrag > 0:
            out[row["name"]] = round(betrag, 2)
    return out


def filter_konsum(betraege):
    """Entfernt Vermoegensumschichtungen - die gehoeren nicht in den Ausgabenvergleich."""
    return {k: v for k, v in betraege.items() if k not in NICHT_KONSUM}


def parse_income(payload, kategorie=EINKOMMEN_KATEGORIE):
    """insight/income/category -> eingenommene Euro dieser einen Kategorie.

    Bewusst NICHT die Summe aller Eingaenge: Rueckzahlungen, Erstattungen und
    Umbuchungen vom eigenen Bargeld sind kein Einkommen und wuerden die
    Sparquote schoenrechnen.
    """
    for row in payload:
        if row.get("name") == kategorie:
            return round(abs(float(row.get("difference_float") or 0.0)), 2)
    return 0.0


def sparquote(einnahmen, konsum):
    """Anteil der Einnahmen in Prozent, der nicht verkonsumiert wurde.

    Negativ heisst: es wurde mehr ausgegeben als eingenommen.
    """
    if einnahmen <= 0:
        return None
    return round((einnahmen - konsum) / einnahmen * 100, 1)


def _trend(delta_prozent, vormonat):
    if vormonat == 0:
        return "neu"
    if delta_prozent >= TREND_SCHWELLE_PROZENT:
        return "gestiegen"
    if delta_prozent <= -TREND_SCHWELLE_PROZENT:
        return "gesunken"
    return "stabil"


def build_report_json(aktuell, vormonat, monat, einnahmen=None, einnahmen_vor=None):
    """Fertig gerechneter Monatsbericht. Die KI bekommt genau dieses Dict."""
    gesamt = round(sum(aktuell.values()), 2)
    gesamt_vor = round(sum(vormonat.values()), 2)

    kategorien = []
    for name, betrag in sorted(aktuell.items(), key=lambda kv: kv[1], reverse=True):
        vor = vormonat.get(name, 0.0)
        delta = round(betrag - vor, 2)
        prozent = round(delta / vor * 100, 1) if vor else None
        kategorien.append({
            "name": name,
            "betrag_euro": round(betrag, 2),
            "vormonat_euro": round(vor, 2),
            "delta_euro": delta,
            "delta_prozent": prozent,
            "anteil_prozent": round(betrag / gesamt * 100, 1) if gesamt else 0.0,
            "trend": _trend(prozent if prozent is not None else 0.0, vor),
        })

    return {
        "monat": monat,
        "waehrung": "EUR",
        "gesamtausgaben_euro": gesamt,
        "vormonat_gesamt_euro": gesamt_vor,
        "delta_gesamt_euro": round(gesamt - gesamt_vor, 2),
        "delta_gesamt_prozent": (round((gesamt - gesamt_vor) / gesamt_vor * 100, 1)
                                 if gesamt_vor else None),
        "einnahmen_euro": round(einnahmen, 2) if einnahmen is not None else None,
        "sparquote_prozent": (sparquote(einnahmen, gesamt)
                              if einnahmen is not None else None),
        # Vergleichswert, damit die KI "gestiegen/gesunken" nicht raten muss.
        "sparquote_vormonat_prozent": (sparquote(einnahmen_vor, gesamt_vor)
                                       if einnahmen_vor is not None else None),
        "kategorien": kategorien,
        "top_3": [k["name"] for k in kategorien[:3]],
    }


def format_push(report, ki):
    """Bericht + KI-Antwort -> Push-Text (ntfy, Plaintext)."""
    zeilen = [ki.get("zusammenfassung", "").strip(), ""]
    zeilen.append(f"Ausgaben {report['monat']}: {report['gesamtausgaben_euro']:.2f} EUR")
    if report["delta_gesamt_prozent"] is not None:
        zeilen.append(f"Vormonat: {report['delta_gesamt_euro']:+.2f} EUR "
                      f"({report['delta_gesamt_prozent']:+.1f} %)")
    if report.get("einnahmen_euro"):
        zeilen.append(f"Einnahmen: {report['einnahmen_euro']:.2f} EUR")
    if report.get("sparquote_prozent") is not None:
        zeilen.append(f"Uebrig: {report['sparquote_prozent']:+.1f} % der Einnahmen")
    zeilen.append("")
    for k in report["kategorien"][:5]:
        zeilen.append(f"- {k['name']}: {k['betrag_euro']:.2f} EUR ({k['trend']})")
    tipps = ki.get("tipps") or []
    if tipps:
        zeilen.append("")
        zeilen.append("Tipps:")
        zeilen.extend(f"* {t}" for t in tipps[:3])
    return "\n".join(zeilen).strip()


# ---------- I/O ----------
def fetch_expenses(base, token, start, end):
    r = requests.get(
        f"{base.rstrip('/')}/api/v1/insight/expense/category",
        params={"start": start, "end": end},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=60)
    r.raise_for_status()
    return filter_konsum(parse_insight(r.json()))


def fetch_income(base, token, start, end):
    """Echtes Einkommen im Zeitraum (nur die Kategorie "Einkommen")."""
    r = requests.get(
        f"{base.rstrip('/')}/api/v1/insight/income/category",
        params={"start": start, "end": end},
        headers={"Authorization": f"Bearer {token}", "Accept": "application/json"},
        timeout=60)
    r.raise_for_status()
    return parse_income(r.json())


def ask_ollama(report, url, model):
    payload = {
        "model": model,
        "system": ADVISOR_SYSTEM_PROMPT,
        "prompt": json.dumps(report, ensure_ascii=False),
        "stream": False,
        "format": "json",
        "options": {"temperature": 0.2, "num_predict": 400},
    }
    r = requests.post(url, json=payload, timeout=300)
    r.raise_for_status()
    try:
        return json.loads(r.json().get("response", "{}"))
    except json.JSONDecodeError:
        return {}


def send_ntfy(text, url, token="", user="", password=""):
    """Schickt den Bericht an ntfy.

    ntfy laeuft mit auth-default-access: deny-all, weil es von aussen
    erreichbar ist. Ohne Anmeldung antwortet es mit 403. Ein Token hat
    Vorrang, sonst wird Basic-Auth aus Benutzer und Passwort gebaut.
    """
    headers = {"Title": "Finanzbericht", "Tags": "moneybag", "Priority": "default"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    elif user and password:
        paar = base64.b64encode(f"{user}:{password}".encode("utf-8")).decode("ascii")
        headers["Authorization"] = f"Basic {paar}"
    r = requests.post(url, data=text.encode("utf-8"), headers=headers, timeout=30)
    r.raise_for_status()


def run(today=None):
    today = today or datetime.date.today()
    t0 = time.perf_counter()
    m = JobMetrics("advisor")
    try:
        base, pat = os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"]

        start, end = previous_month_range(today)
        vor_start, vor_end = month_before_range(start)

        aktuell = fetch_expenses(base, pat, start, end)
        vormonat = fetch_expenses(base, pat, vor_start, vor_end)
        einnahmen = fetch_income(base, pat, start, end)
        einnahmen_vor = fetch_income(base, pat, vor_start, vor_end)
        report = build_report_json(aktuell, vormonat, start[:7],
                                   einnahmen=einnahmen, einnahmen_vor=einnahmen_vor)

        if report["gesamtausgaben_euro"] == 0:
            m.record_success(time.perf_counter() - t0)
            m.save()
            slog.log_event("advisor_run_empty", monat=report["monat"])
            print(f"Keine Ausgaben in {report['monat']}, kein Bericht.")
            return

        # Der Berater formuliert Fliesstext -> groesseres Modell, falls konfiguriert.
        model = os.environ.get("OLLAMA_MODEL_ADVISOR") or os.environ["OLLAMA_MODEL"]
        ki = ask_ollama(report, os.environ["OLLAMA_URL"], model)
        text = format_push(report, ki)
        try:
            send_ntfy(text, os.environ["NTFY_URL"],
                      os.environ.get("NTFY_TOKEN", ""),
                      os.environ.get("NTFY_USER", ""),
                      os.environ.get("NTFY_PASSWORD", ""))
            m.inc("finance_ntfy_push_success_total")
        except Exception:
            m.inc("finance_ntfy_push_failed_total")
            raise

        m.record_success(time.perf_counter() - t0)
        m.save()
        # KEINE Betraege ins Log - nur Zaehl-/Struktur-Infos.
        slog.log_event("advisor_run_success", monat=report["monat"],
                       kategorien=len(report["kategorien"]),
                       tipps=len(ki.get("tipps") or []))
        print(f"Finanzbericht {report['monat']} gesendet ({report['gesamtausgaben_euro']:.2f} EUR).")
    except Exception as e:
        m.record_failure(time.perf_counter() - t0)
        m.save()
        slog.log_event("advisor_run_failed", error_type=type(e).__name__)
        raise


if __name__ == "__main__":
    run()
