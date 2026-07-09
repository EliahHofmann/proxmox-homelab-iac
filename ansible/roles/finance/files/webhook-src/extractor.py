"""Ruft die lokale Ollama-KI und parst robust striktes Finanz-JSON."""
import json
import datetime
import requests

SYSTEM_PROMPT = (
    "Du bist ein Finanz-Extraktor. Antworte AUSSCHLIESSLICH mit gueltigem JSON, kein Fliesstext. "
    "Schluessel exakt: haendler (string), betrag_euro (number, positiv), datum (YYYY-MM-DD), kategorie (string). "
    "Regeln: betrag_euro = Gesamt-/Zahlbetrag als positive Dezimalzahl (Punkt als Trenner). "
    "Wenn unklar: haendler=Unbekannt, betrag_euro=0, kategorie=Sonstiges. Erfinde niemals Betraege. "
    'Beispiel: {"haendler":"Amazon","betrag_euro":19.99,"datum":"2026-07-05","kategorie":"Elektronik"}'
)


def parse_ai_json(raw):
    today = datetime.date.today().isoformat()
    defaults = {"haendler": "Unbekannt", "betrag_euro": 0.0, "datum": today, "kategorie": "Sonstiges"}
    try:
        data = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return defaults
    if not isinstance(data, dict):
        return defaults
    out = dict(defaults)
    if data.get("haendler"):
        out["haendler"] = str(data["haendler"])[:100]
    if data.get("kategorie"):
        out["kategorie"] = str(data["kategorie"])
    if data.get("datum"):
        try:
            datetime.date.fromisoformat(str(data["datum"]))
            out["datum"] = str(data["datum"])
        except ValueError:
            pass
    betrag = data.get("betrag_euro", 0)
    try:
        cleaned = str(betrag).replace(",", ".").replace("€", "").replace("EUR", "").strip()
        out["betrag_euro"] = round(abs(float(cleaned)), 2)
    except (ValueError, TypeError):
        out["betrag_euro"] = 0.0
    return out


def extract_finance(ocr_text, ollama_url, model):
    prompt = f"{SYSTEM_PROMPT}\nText: {ocr_text[:1500]}"
    payload = {
        "model": model, "prompt": prompt, "stream": False, "format": "json",
        "options": {"temperature": 0.1, "num_predict": 200},
    }
    r = requests.post(ollama_url, json=payload, timeout=120)
    r.raise_for_status()
    return parse_ai_json(r.json().get("response", ""))
