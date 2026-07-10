"""KI-Finanzberater (Strom 3): Kategorie-Summen -> Ollama -> ntfy-Push.

Laeuft monatlich per Cron. Alle Zahlen (Deltas, Prozente, Anteile) werden hier
in Python berechnet; die KI darf ausschliesslich interpretieren, nicht rechnen.
Das ist der Halluzinationsschutz fuer das 8B-Modell.
"""
import os
import json
import datetime
import requests

# Ab welcher Abweichung eine Kategorie als gestiegen/gesunken gilt
TREND_SCHWELLE_PROZENT = 5.0

ADVISOR_SYSTEM_PROMPT = """Du bist ein nuechterner Finanzberater fuer einen Privathaushalt.

Du bekommst einen fertig berechneten Monatsbericht als JSON. ALLE Zahlen darin
sind bereits korrekt berechnet.

REGELN:
1. Rechne NIEMALS selbst. Uebernimm Zahlen ausschliesslich woertlich aus dem JSON.
2. Erfinde keine Kategorien, Betraege oder Zeitraeume, die nicht im JSON stehen.
3. Wenn eine Angabe fehlt, erwaehne sie nicht. Sage nicht, dass sie fehlt.
4. Keine Anlageberatung, keine Versicherungs- oder Kreditempfehlungen.
5. Antworte auf Deutsch, sachlich, ohne Floskeln und ohne Anrede.

Antworte AUSSCHLIESSLICH mit gueltigem JSON in exakt dieser Form:
{
  "zusammenfassung": "Ein bis zwei Saetze zum Gesamtbild.",
  "tipps": ["Konkreter Tipp 1", "Konkreter Tipp 2", "Konkreter Tipp 3"]
}

Die Tipps beziehen sich auf die Kategorien mit dem Trend "gestiegen" oder auf
die groessten Posten aus "top_3". Maximal 3 Tipps, je maximal 20 Woerter."""


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


def _trend(delta_prozent, vormonat):
    if vormonat == 0:
        return "neu"
    if delta_prozent >= TREND_SCHWELLE_PROZENT:
        return "gestiegen"
    if delta_prozent <= -TREND_SCHWELLE_PROZENT:
        return "gesunken"
    return "stabil"


def build_report_json(aktuell, vormonat, monat):
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
    return parse_insight(r.json())


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


def send_ntfy(text, url, token=""):
    headers = {"Title": "Finanzbericht", "Tags": "moneybag", "Priority": "default"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    r = requests.post(url, data=text.encode("utf-8"), headers=headers, timeout=30)
    r.raise_for_status()


def run(today=None):
    today = today or datetime.date.today()
    base, pat = os.environ["FIREFLY_URL"], os.environ["FIREFLY_PAT"]

    start, end = previous_month_range(today)
    vor_start, vor_end = month_before_range(start)

    aktuell = fetch_expenses(base, pat, start, end)
    vormonat = fetch_expenses(base, pat, vor_start, vor_end)
    report = build_report_json(aktuell, vormonat, start[:7])

    if report["gesamtausgaben_euro"] == 0:
        print(f"Keine Ausgaben in {report['monat']}, kein Bericht.")
        return

    ki = ask_ollama(report, os.environ["OLLAMA_URL"], os.environ["OLLAMA_MODEL"])
    text = format_push(report, ki)
    send_ntfy(text, os.environ["NTFY_URL"], os.environ.get("NTFY_TOKEN", ""))
    print(f"Finanzbericht {report['monat']} gesendet ({report['gesamtausgaben_euro']:.2f} EUR).")


if __name__ == "__main__":
    run()
